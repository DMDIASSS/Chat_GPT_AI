"""Contact -> stationary reach-time possession -> predicted possession.

An independent curriculum experiment, not a reconstruction of an unpublished
reward. Policies have the existing 109/90 observation/action contract.
"""
import copy
import numpy as np
from .potential import estimate,reach_times
from .observation import ACTIONS

STAGES=('contact','possession','trajectory')
RECIPE={
    'version':'contact-possession-v1','checkpoint_steps':500_000,
    'contact_min_steps':500_000,'contact_max_steps':2_000_000,
    'possession_min_steps':1_000_000,'possession_max_steps':4_000_000,
    'contact_success_required':.85,'contact_median_seconds_max':2.5,
    'race_score_required':.55,'probe_pairs':32,'probe_seconds':6.,
    'possession_rate_per_second':.04,'first_touch_bonus':.15,
    'lead_temperature':.6,'lead_cap_seconds':1.5,
    'trial_seconds':6.,'contact_approach_weight':.02,
    'contact_first_touch_bonus':1.,'contact_discount_seconds':3.,
    'contact_drill_fraction':.8,'possession_drill_fraction':.35,'contact_ground_only':True,
    'kl_target':.003,'lr_min':1e-5,'lr_max':3e-4,
}

def validate_recipe(cfg):
    a=cfg['acquisition']
    if a['stage'] not in STAGES or a['version']!=RECIPE['version']:
        raise ValueError('Unknown acquisition recipe/stage')
    if not 0<=a['drill_fraction']<=.8 or a['trial_seconds']!=6.:
        raise ValueError('Invalid acquisition drill bounds')
    # Bound the infinite discounted possession cost below one goal. This
    # discourages intentionally conceding just to escape a negative lead.
    dt=cfg['tick_skip']/120
    if not 0<a['possession_rate_per_second']*dt/(1-cfg['ppo']['gamma'])<.75:
        raise ValueError('Possession reward can outweigh the goal objective')
    if not (0<a['lr_min']<=a['lr_max']<=3e-4 and .001<=a['kl_target']<=.01):
        raise ValueError('Invalid acquisition KL controller bounds')
    if cfg.get('predictive',{}).get('enabled') or cfg.get('bootstrap',{}).get('enabled'):
        raise ValueError('Acquisition excludes stacking the old shaping rewards')
    return a

def stage_config(parent,stage):
    if stage not in STAGES:raise ValueError('Unknown stage')
    cfg=copy.deepcopy(parent)
    cfg.update(version=RECIPE['version'],objective='acquisition_'+stage)
    cfg['predictive']={'enabled':False};cfg['bootstrap']={'enabled':False}
    cfg['rewards']['impulse']=0
    cfg['ppo'].pop('entropy_schedule',None)
    cfg['ppo'].update(learning_rate=5e-5,entropy=.003)
    cfg['league'].update(history_fraction=0. if stage=='contact' else .25,nexto_fraction=0.)
    cfg['acquisition']={k:RECIPE[k] for k in (
        'version','possession_rate_per_second','first_touch_bonus',
        'lead_temperature','lead_cap_seconds','trial_seconds',
        'contact_approach_weight','contact_first_touch_bonus','contact_discount_seconds','contact_ground_only',
        'kl_target','lr_min','lr_max')}
    cfg['acquisition'].update(stage=stage,drill_fraction=RECIPE.get(stage+'_drill_fraction',0.))
    validate_recipe(cfg)
    return cfg

def adapt_learning_rate(optimizer,cfg,kl):
    """Conservative dead-band KL controller; actual rate lives in Adam state."""
    a=cfg['acquisition'];factor=1.1 if kl<a['kl_target']*.5 else .8 if kl>a['kl_target']*2 else 1.
    for group in optimizer.param_groups:
        group['lr']=float(np.clip(group['lr']*factor,a['lr_min'],a['lr_max']))
    return optimizer.param_groups[0]['lr']

def drill_states(rng,n,moving=False):
    """Ground contact races with random location, heading, boost and velocity.

    Both cars use identical distributions; orientation is a proper basis.
    These state injections are training/probe resets only, never observations.
    """
    w=np.zeros((n,3,32),np.float32)
    w[:,0,:3]=np.column_stack([rng.uniform(-1300,1300,n),rng.uniform(-1800,1800,n),np.full(n,94.)])
    if moving:w[:,0,3:5]=rng.uniform(-500,500,(n,2))
    theta=rng.uniform(-np.pi,np.pi,n)
    for side in (0,1):
        angle=theta+side*np.pi+rng.uniform(-.35,.35,n)
        distance=rng.uniform(450,1500,n)
        car=w[:,side+1];car[:,:2]=w[:,0,:2]+np.column_stack([np.cos(angle),np.sin(angle)])*distance[:,None]
        car[:,2]=17
        yaw=angle+np.pi+rng.uniform(-1.2,1.2,n)
        car[:,9:12]=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(n)])
        car[:,12:15]=[0,0,1]
        car[:,3:6]=car[:,9:12]*rng.uniform(0,400,n)[:,None]
        car[:,15]=rng.uniform(33,100,n);car[:,16]=car[:,29]=1
    return w

def possession(world,cfg):
    a=cfg['acquisition']
    if a['stage']=='trajectory':
        pc={'predictive':{'horizon':3.,'samples':16,'temperature':a['lead_temperature'],
                          'intercept_weight':1.,'threat_weight':0.}}
        out=estimate(world,pc);eta,reachable=out['eta'],out['reachable']
    else:
        # First isolate reaching a stationary target. No moving-ball forecast
        # enters this stage's target path.
        times=np.linspace(0,3,17,dtype=np.float32)
        points=np.repeat(world[:,0:1,:3],len(times),axis=1)
        eta,reachable=reach_times(world,points,times)
    lead=np.clip(eta[:,1]-eta[:,0],-a['lead_cap_seconds'],a['lead_cap_seconds'])
    value=np.tanh(lead/a['lead_temperature'])
    value[~reachable.any(-1)]=0
    return value.astype(np.float32),eta,reachable

def reward_components(cfg,before,raw,elapsed,seen):
    """True contacts once per car/episode, finite time-scaled possession.

    Part 0 = goals, part 1 = contact approach or possession occupancy, part 2 =
    actual first contact. Native goal potential/impulse are replaced, not added.
    """
    a=cfg['acquisition'];stage=a['stage'];dt=raw['info'][:,3]/120
    valid=dt>0;hits=raw['info'][:,1:3]>.5;new=hits&~seen&valid[:,None]
    parts=np.zeros((len(dt),2,3),np.float32)
    parts[:,:,0]=raw['reward_parts'][:,:,0]
    if stage=='contact':
        world=raw['final_world'];delta=world[:,0:1,:3]-world[:,1:,:3]
        direction=delta/np.maximum(1.,np.linalg.norm(delta,axis=-1,keepdims=True))
        toward=np.maximum(0.,(world[:,1:,3:6]*direction).sum(-1)/2300.)
        parts[:,:,1]=a['contact_approach_weight']*toward.clip(0,1)*(dt/(cfg['tick_skip']/120))[:,None]
        parts[:,:,1]*=world[:,1:,20]<.5
        parts[:,:,2]=new*a['contact_first_touch_bonus']*np.exp(-elapsed/a['contact_discount_seconds'])[:,None]
        metrics={}
    else:
        lead,eta,reachable=possession(raw['final_world'],cfg)
        parts[:,0,1]=a['possession_rate_per_second']*dt*lead
        parts[:,1,1]=-parts[:,0,1]
        parts[:,:,2]=new*a['first_touch_bonus']
        metrics={'eta_mean':float(eta.mean()),'reachable_fraction':float(reachable.mean()),
                 'lead_abs_mean':float(np.abs(lead).mean())}
    if not np.isfinite(parts).all():raise FloatingPointError('Nonfinite acquisition rewards')
    return parts,new,metrics

class AcquisitionBatch:
    """Training-only wrapper. Evaluation/watch retain ordinary native matches."""
    def __init__(self,env,cfg,seed):
        self.env=env;self.cfg=cfg;self.a=validate_recipe(cfg)
        self.rng=np.random.default_rng(seed ^ 0xA31C09)
        self.raw=env.observe();n=len(self.raw['world'])
        self.drill=np.zeros(n,bool);self.elapsed=np.zeros(n,np.float32)
        self.seen=np.zeros((n,2),bool);self.last={};self.last_probe={}
        self._reset(np.arange(n))

    def __getattr__(self,name):return getattr(self.env,name)
    def observe(self):return self.raw

    def _drill_mask(self,raw):
        if self.a['stage']=='contact' and self.a['contact_ground_only']:
            raw['mask']=raw['mask'].copy()
            raw['mask'][self.drill]&=(ACTIONS[:,5]==0)[None,None,:]
            if not raw['mask'].any(-1).all():raise RuntimeError('Contact drill mask left an empty action set')
        return raw

    def _reset(self,indices):
        if not len(indices):return
        chosen=self.rng.random(len(indices))<self.a['drill_fraction']
        self.drill[indices]=chosen;self.elapsed[indices]=0;self.seen[indices]=False
        ids=np.asarray(indices)[chosen]
        if len(ids):
            states=drill_states(self.rng,len(ids),moving=self.a['stage']!='contact')
            for i,state in zip(ids,states):self.env.inject(int(i),state)
        self.raw=self._drill_mask(self.env.observe())

    def step(self,actions,remaining_ticks=None):
        before=self.raw['world'];raw=self.env.step(actions) if remaining_ticks is None else self.env.step(actions,remaining_ticks)
        self.elapsed+=raw['info'][:,3]/120
        hit=(raw['info'][:,1:3]>.5).any(-1)
        # Contact drills end on the first physical hit or the fixed deadline.
        # Deadline is an actual finite-task terminal, not a time-limit bootstrap.
        custom=self.drill&((hit if self.a['stage']=='contact' else False)|(self.elapsed>=self.a['trial_seconds']))
        native_done=raw['terminated']|raw['truncated'];done=native_done|custom
        raw['terminated']=raw['terminated']|custom
        raw['truncated']=raw['truncated']&~custom
        parts,new,metrics=reward_components(self.cfg,before,raw,self.elapsed,self.seen)
        self.seen|=new;raw['reward_parts']=parts;raw['rewards']=parts.sum(-1)
        self.last={**metrics,'first_contacts':int(new.sum()),'drill_fraction':float(self.drill.mean()),
                   'completed_drills':int((done&self.drill).sum()),'successful_drills':int((done&self.drill&hit).sum())}
        ids=np.flatnonzero(done)
        # Native has already reset its own terminals. Explicitly reset only
        # custom terminals, then select the next curriculum scene. Preserve
        # final_* for PPO's GAE/timeout contract.
        for i in np.flatnonzero(custom&~native_done):self.env.reset_one(int(i))
        if len(ids):
            self._reset(ids)
            for key in ('world','pads','obs','mask'):raw[key]=self.raw[key]
        raw=self._drill_mask(raw);self.raw=raw
        return raw
