"""No-boost ground race against a deadline, with physical dodge/contact checks."""
import numpy as np
from .acquisition import AcquisitionBatch,reward_components
from .observation import ACTIONS

NEUTRAL=int(np.flatnonzero(np.all(ACTIONS==0,axis=1))[0])
VERSION='ground-flip-v1'
RECIPE={'version':VERSION,'ticks':264,'distance_min':2240.,'distance_max':2260.,
        'drill_fraction':.5,'drill_entropy':.02,'failure_scale':1.,'failure_floor':.01}

def drill_states(rng,n,colors=None):
    colors=np.asarray(colors if colors is not None else rng.integers(2,size=n),np.int64)
    w=np.zeros((n,3,32),np.float32)
    # Diagonal lanes avoid boost pads on the intended path. Boost actions stay
    # disabled even if an exploratory detour happens to collect a pad.
    angle=np.pi/4+rng.integers(4,size=n)*np.pi/2+rng.uniform(-.08,.08,n)
    direction=np.column_stack([np.cos(angle),np.sin(angle),np.zeros(n)])
    center=np.column_stack([rng.uniform(-50,50,(n,2)),np.zeros(n)])
    distance=rng.uniform(RECIPE['distance_min'],RECIPE['distance_max'],n)
    w[:,0,:3]=center+direction*(distance/2)[:,None];w[:,0,2]=94
    for i,color in enumerate(colors):
        active=w[i,color+1];active[:3]=center[i]-direction[i]*distance[i]/2;active[2]=17
        active[9:12]=direction[i];active[12:15]=[0,0,1];active[16]=active[29]=1
        parked=w[i,2-color];parked[:3]=[3000,3000,17]
        parked[9:12]=[1,0,0];parked[12:15]=[0,0,1];parked[16]=parked[29]=1
    return w,colors

def terminal_penalty(distance,initial_distance,success,scale=1.,floor=.01):
    ratio=np.clip(np.asarray(distance)/np.maximum(np.asarray(initial_distance),1),floor,1)
    return np.where(success,0.,-scale*ratio).astype(np.float32)

class GroundFlipBatch(AcquisitionBatch):
    def __init__(self,env,cfg,seed,force=False,color=None):
        self.f=cfg['flip_drill'];self.force=force;self.watch_color=color
        if color not in (None,0,1):raise ValueError('Invalid drill color')
        if self.f!=RECIPE:raise ValueError('Unknown/changed ground-flip recipe; use a new version')
        n=len(env.observe()['world']);self.colors=np.zeros(n,np.int64)
        self.trial_ticks=np.zeros(n,np.int64);self.flipped=np.zeros(n,bool)
        self.initial_distance=np.ones(n,np.float32)
        order=np.random.default_rng(seed ^ 0xF11F).permutation(n)
        self.drill_ids=order[:n if force else round(n*.5)]
        super().__init__(env,cfg,seed)

    def learner_rows(self):
        rows=np.ones((len(self.drill),2),bool);ids=np.flatnonzero(self.drill)
        rows[ids,1-self.colors[ids]]=False;return rows

    def entropy_coefficients(self):
        c=np.where(self.drill,self.f['drill_entropy'],self.cfg['ppo']['entropy'])
        return np.repeat(c[:,None],2,axis=1).astype(np.float32)

    def _mask(self,raw,final=False):
        key='final_mask' if final else 'mask';raw[key]=raw[key].copy()
        raw[key][self.drill]&=(ACTIONS[:,6]==0)[None,None,:]
        ids=np.flatnonzero(self.drill);parked=1-self.colors[ids]
        raw[key][ids,parked]=False;raw[key][ids,parked,NEUTRAL]=True
        return raw

    def _reset(self,indices):
        if not len(indices):return
        assignment=np.zeros(len(self.drill),bool);assignment[self.drill_ids]=True
        self.drill[indices]=assignment[indices]
        self.trial_ticks[indices]=0;self.elapsed[indices]=0;self.seen[indices]=False;self.flipped[indices]=False
        ids=np.asarray(indices)[self.drill[indices]]
        chosen=None if self.watch_color is None else np.full(len(ids),self.watch_color,np.int64)
        w,colors=drill_states(self.rng,len(ids),colors=chosen)
        self.colors[ids]=colors
        for i,state in zip(ids,w):self.env.inject(int(i),state)
        self.raw=self._mask(self.env.observe())
        self.initial_distance[indices]=np.linalg.norm(self.raw['world'][indices,self.colors[indices]+1,:3]-self.raw['world'][indices,0,:3],axis=-1)

    def step(self,actions,remaining_ticks=None):
        actions=np.asarray(actions,np.int64);n=len(self.drill);ix=np.arange(n)
        if actions.shape!=(n,2) or ((actions<0)|(actions>=len(ACTIONS))).any():raise ValueError('Invalid actions')
        before=self.raw['world'];budget=np.full(n,8,np.int64)
        budget[self.drill]=np.minimum(8,self.f['ticks']-self.trial_ticks[self.drill])
        if remaining_ticks is not None:budget=np.minimum(budget,np.asarray(remaining_ticks,np.int64))
        checked=self.drill&(budget>0)
        if not self.raw['mask'][ix[:,None],np.arange(2),actions][checked].all():
            raise ValueError('Drill requires legal no-boost actions and neutral parked car')
        raw=self.env.step(actions,budget);dt=raw['info'][:,3].astype(np.int64)
        self.trial_ticks+=dt;self.elapsed+=dt/120;active=self.colors;valid=dt>0
        self.flipped|=valid&(raw['final_world'][ix,active+1,31]>.5)
        contact=valid&(raw['info'][ix,active+1]>.5)
        success=self.drill&contact&self.flipped
        custom=self.drill&valid&(contact|(self.trial_ticks>=self.f['ticks']))
        native=raw['terminated']|raw['truncated'];done=native|custom
        raw['terminated']|=custom;raw['truncated']&=~custom
        parts=np.zeros_like(raw['reward_parts']);parts[:,:,0]=raw['reward_parts'][:,:,0]
        normal=~self.drill
        if normal.any():
            sub={k:raw[k][normal] for k in ('info','final_world','reward_parts','terminated')}
            base,new,_=reward_components(self.cfg,before[normal],sub,self.elapsed[normal],self.seen[normal])
            parts[normal]=base;self.seen[normal]|=new
        distance=np.linalg.norm(raw['final_world'][ix,active+1,:3]-raw['final_world'][:,0,:3],axis=-1)
        completed=done&self.drill
        penalties=terminal_penalty(distance,self.initial_distance,success,self.f['failure_scale'],self.f['failure_floor'])
        ids=np.flatnonzero(completed);parts[ids,active[ids],2]=penalties[ids]
        raw['reward_parts']=parts;raw['rewards']=parts.sum(-1)
        self.last={'completed_trials':int(completed.sum()),'successes':int((completed&success).sum()),
                   'physical_flips':int((completed&self.flipped).sum()),
                   'nonflip_contacts':int((completed&contact&~self.flipped).sum()),
                   'failure_distance_sum':float(distance[completed&~success].sum()),
                   'drill_fraction':float(self.drill.mean())}
        raw['flip_drill']={'completed':completed.copy(),'success':success.copy(),'flipped':self.flipped.copy(),
                           'color':active.copy(),'ticks':self.trial_ticks.copy(),'distance':distance,'penalty':penalties}
        self._mask(raw,final=True)
        for i in np.flatnonzero(custom&~native):self.env.reset_one(int(i))
        if done.any():
            self._reset(np.flatnonzero(done))
            for k in ('world','pads','obs','mask'):raw[k]=self.raw[k]
        else:self._mask(raw)
        self.raw=raw;return raw
