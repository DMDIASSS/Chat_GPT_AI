"""Bounded, zero-sum interception potential. No action or touch bonuses.

Reachability is a fast kinematic estimate, not an exact first-touch solver.
Predictions are stateless: no stale cache enters the reward definition.
"""
import numpy as np

BALL_RADIUS=93.15

def ball_prediction(world,horizon=3.,samples=24):
    # Vectorized ballistic prediction with radius-aware arena planes. Rounded
    # corners, ramps and goal-post collisions are flagged as uncertain.
    w=np.asarray(world,np.float32);dt=horizon/samples;n=len(w)
    pos=w[:,0,:3].copy();vel=w[:,0,3:6].copy();spin=w[:,0,6:9].copy();points=[pos.copy()];quality=np.ones(n,bool);goals=np.zeros((n,samples+1),np.int8)
    def friction(mask,normal,impulse):
        contact=-BALL_RADIUS*np.asarray(normal,np.float32);slip=vel+np.cross(spin,contact)
        tangent=slip-(slip*np.asarray(normal)).sum(-1)[:,None]*np.asarray(normal)
        change=-tangent/3.5;mag=np.linalg.norm(change,axis=-1)
        change*=np.minimum(1.,.35*np.asarray(impulse)/np.maximum(mag,1e-8))[:,None];change[~mask]=0
        vel[:]+=change;spin[:]+=np.cross(contact,change)/(.4*BALL_RADIUS**2)
        return change
    for j in range(samples):
        vel*=np.float32(.97**dt)
        oldz=pos[:,2].copy();oldvz=vel[:,2].copy();pos+=vel*dt;pos[:,2]-=325*dt*dt;vel[:,2]-=650*dt
        floor=pos[:,2]<BALL_RADIUS
        if np.any(floor):
            impact=np.clip((oldvz+np.sqrt(np.maximum(0,oldvz**2+1300*np.maximum(0,oldz-BALL_RADIUS))))/650,0,dt);remaining=dt-impact;incoming=oldvz-650*impact;up=-.6*incoming
            settled=floor&(np.abs(incoming)<100);pos[floor,2]=np.maximum(BALL_RADIUS,(BALL_RADIUS+up*remaining-325*remaining**2)[floor]);vel[floor,2]=(up-650*remaining)[floor];pos[settled,2]=BALL_RADIUS;vel[settled,2]=0
            impulse=np.where(settled,650*dt,np.abs(incoming)*1.6);change=friction(floor,[0,0,1],impulse);pos[:,:2]+=change[:,:2]*np.where(settled,dt*.5,remaining)[:,None]
        ceiling=pos[:,2]>2044-BALL_RADIUS;pos[ceiling,2]=2*(2044-BALL_RADIUS)-pos[ceiling,2];impulse=np.abs(vel[:,2])*1.6;vel[ceiling,2]=-np.abs(vel[ceiling,2])*.6;friction(ceiling,[0,0,-1],impulse)
        for axis,limit in ((0,4096-BALL_RADIUS),(1,5120-BALL_RADIUS)):
            hit=np.abs(pos[:,axis])>limit
            if axis==1:
                mouth=(np.abs(pos[:,0])<892-BALL_RADIUS)&(pos[:,2]<642-BALL_RADIUS)
                crossing=(np.abs(pos[:,axis])>5120+BALL_RADIUS)&mouth;goals[crossing,j+1]=np.sign(pos[crossing,1]).astype(np.int8)
                hit&=~mouth
            if np.any(hit):
                pos[hit,axis]=np.sign(pos[hit,axis])*(2*limit-np.abs(pos[hit,axis]));impulse=np.abs(vel[:,axis])*1.6;vel[hit,axis]*=-.6
                # Contact normal sign determines spin transfer at each wall.
                for direction in (-1,1):
                    subset=hit&(pos[:,axis]*direction>0);normal=[0,0,0];normal[axis]=-direction;friction(subset,normal,impulse)
        quality&=~((np.abs(pos[:,0])>2900)&(np.abs(pos[:,1])>3900))
        quality&=~((pos[:,2]<210)&((np.abs(pos[:,0])>3700)|(np.abs(pos[:,1])>4700)))
        spin*=np.minimum(1.,6./np.maximum(np.linalg.norm(spin,axis=-1),1e-8))[:,None]
        points.append(pos.copy())
    return np.stack(points,axis=1),np.linspace(0,horizon,samples+1,dtype=np.float32),goals,quality

def reach_times(world,points,times):
    """Both players share the same target path; evaluate forward/reverse modes.

    The acceleration envelope integrates speed-dependent throttle, finite boost
    and braking; turn delay and lost lateral momentum reduce available reach.
    Height feasibility accounts for gravity, jump budget and boost budget.
    Flip speed impulses/wall driving are not modeled: those estimates remain
    uncertain rather than falsely certified physically feasible.
    """
    cars=np.asarray(world,np.float32)[:,1:];p=points[:,None,:,:];t=times[None,None,:]
    delta=p-cars[:,:,None,:3];dxy=np.linalg.norm(delta[:,:,:,:2],axis=-1);unit=delta[:,:,:,:2]/np.maximum(dxy[:,:,:,None],1.)
    forward=cars[:,:,9:11];forward=forward/np.maximum(np.linalg.norm(forward,axis=-1,keepdims=True),.05)
    heading=np.sum(unit*forward[:,:,None,:],axis=-1).clip(-1,1);theta=np.arccos(heading)
    velocity=cars[:,:,3:5];speed=np.linalg.norm(velocity,axis=-1);along=np.sum(velocity[:,:,None,:]*unit,axis=-1)
    ground=cars[:,:,16]>.5;boost=cars[:,:,15].clip(0,100);can=cars[:,:,29]>.5
    # Ground turn rate decreases with speed; airborne turns are uncertain.
    turn_rate=np.clip(3.2-speed*.0008,1.1,3.2)[:,:,None]
    best=np.zeros_like(dxy)
    for reverse in (False,True):
        angle=np.pi-theta if reverse else theta
        turn=angle/turn_rate;available=np.maximum(0,t-turn)
        initial=np.maximum(0,along)*np.exp(-angle*.7)
        v=np.minimum(initial,1200. if reverse else 2300.);travel=np.zeros_like(v);budget=np.broadcast_to(boost[:,:,None],v.shape).copy()
        # Fixed integration work; each cell is a different interception time.
        for _ in range(8):
            dt=available/8.;throttle=1600*np.clip(1-v/1410.,0,1)
            if reverse:throttle=1100*np.clip(1-v/1200.,0,1)
            spend=np.minimum(budget,dt*33.3) if not reverse else np.zeros_like(budget)
            pitch_fraction=dxy/np.maximum(np.linalg.norm(delta,axis=-1),1.)
            acc_boost=np.divide(spend,33.3*dt,out=np.zeros_like(spend),where=dt>0)*991.7*pitch_fraction
            vn=np.minimum(1200. if reverse else 2300.,v+(throttle+acc_boost)*dt)
            travel+=(v+vn)*.5*dt;v=vn;budget-=spend
        # While turning, retain only useful current motion; no free teleport.
        travel+=np.maximum(0,along)*np.minimum(t,turn)*.35
        best=np.maximum(best,travel)
    z=cars[:,:,2,None];vz=cars[:,:,5,None];tt=t
    airborne=~ground;fall=z+vz*tt-325*tt*tt
    jump_time=np.maximum(0,tt-.08);hold=np.minimum(jump_time,.2);jump=1458*hold*(jump_time-.5*hold)
    vertical=fall+np.where(can[:,:,None],292*jump_time+np.where(ground[:,:,None],jump+292*np.maximum(0,jump_time-.35),0),0)
    # Optimistic aerial envelope with an explicit finite boost-time budget.
    burn=np.minimum(np.maximum(0,tt-.12),boost[:,:,None]/33.3)
    vertical_fraction=np.maximum(0,delta[:,:,:,2])/np.maximum(np.linalg.norm(delta,axis=-1),1.)
    vertical+=991.7*vertical_fraction*burn*(np.maximum(0,tt-.12)-.5*burn)
    vertical=np.maximum(vertical,z+np.where(ground[:,:,None],0,np.maximum(vz,0)*tt-325*tt*tt))
    height_ok=(p[:,:,:,2]<=np.maximum(z,vertical)+120)&(p[:,:,:,2]>=np.maximum(BALL_RADIUS,fall-160)-120)
    # Ground cars cannot claim high aerials without jump or sufficient momentum.
    height_ok&=~(ground[:,:,None]&~can[:,:,None]&(p[:,:,:,2]>z+120))
    slack=best+125-dxy;feasible=(slack>=0)&height_ok&(cars[:,:,20,None]<.5)
    feasible[:,:,0]&=(np.linalg.norm(delta[:,:,0],axis=-1)<=125)
    hit=feasible.any(-1);idx=feasible.argmax(-1);eta=np.full(hit.shape,float(times[-1]+1),np.float32)
    prev=np.maximum(0,idx-1);take=lambda x,k:np.take_along_axis(x,k[:,:,None],axis=-1).squeeze(-1)
    s0=take(slack,prev);s1=take(slack,idx);fraction=np.clip(-s0/np.maximum(1e-6,s1-s0),0,1)
    interpolated=times[prev]+fraction*(times[idx]-times[prev]);eligible=(idx>0)&take(height_ok,prev)&(s0<0)
    eta=np.where(hit,np.where(eligible,interpolated,times[idx]),eta).astype(np.float32)
    return eta,hit

def estimate_reference(world,cfg):
    p=cfg.get('predictive',{});points,t,goals,quality=ball_prediction(world,p.get('horizon',3.),p.get('samples',24));eta,reachable=reach_times(world,points,t)
    intercept=np.tanh((eta[:,1]-eta[:,0])/p.get('temperature',.6))
    threat=np.zeros(len(world),np.float32)
    for side in (-1,1):
        crossing=goals==side;has=crossing.any(-1);idx=crossing.argmax(-1);arrival=t[idx];defender=1 if side==1 else 0
        margin=np.maximum(0,eta[:,defender]-arrival)
        threat+=side*has*np.tanh(margin/.5)*np.exp(-arrival/2)
    # Suppress speculative plane predictions in corners/ramps, not invent a
    # highly confident aerial/wall controller. Quality itself is deterministic.
    weight=np.ones(len(world),np.float32)
    phi=weight*(p.get('intercept_weight',.8)*intercept+p.get('threat_weight',.2)*threat)
    phi=np.clip(phi,-1,1).astype(np.float32)
    return {'phi':phi,'eta':eta,'reachable':reachable,'intercept':intercept,'threat':threat,'prediction_quality':quality}

def estimate(world,cfg):
    p=cfg.get('predictive',{})
    if not p.get('force_reference',False):
        from . import _native
        if hasattr(_native,'predictive_estimate'):
            return dict(_native.predictive_estimate(np.asarray(world,np.float32),float(p.get('horizon',3.)),int(p.get('samples',24)),float(p.get('temperature',.6)),float(p.get('intercept_weight',.8)),float(p.get('threat_weight',.2))))
    return estimate_reference(world,cfg)


class PotentialReward:
    """One update per true transition; absorbing goals, physical timeouts."""
    def __init__(self,cfg,raw):self.cfg=cfg;self.current=estimate(raw['world'],cfg);self.last={}
    def apply(self,raw):
        nxt=estimate(raw['final_world'],self.cfg);terminal=raw['terminated'];gamma=self.cfg['ppo']['gamma'];weight=self.cfg['predictive']['shaping_weight']
        before=self.current['phi'];after=np.where(terminal,0,nxt['phi']);delta=weight*(gamma*after-before);delta=np.where(raw['info'][:,3]>0,delta,0)
        goal=raw['reward_parts'][:,:,0].copy();parts=np.zeros((len(goal),2,3),np.float32);parts[:,:,0]=goal;parts[:,0,1]=delta;parts[:,1,1]=-delta
        raw['reward_parts']=parts;raw['rewards']=parts.sum(-1)
        self.last={'eta_mean':float(nxt['eta'].mean()),'unreachable_fraction':float((~nxt['reachable']).mean()),'uncertain_prediction_fraction':float((~nxt['prediction_quality']).mean()),'shaping_abs_mean':float(np.abs(delta).mean())}
        done=terminal|raw['truncated'];self.current=nxt
        if np.any(done):
            reset=estimate(raw['world'][done],self.cfg)
            for key in self.current:self.current[key][done]=reset[key]
        return raw


class RewardBatch:
    def __init__(self,env,cfg):
        self.env=env;self.cfg=cfg;self.reward=PotentialReward(cfg,env.observe());self.reward_seconds=0.;self.reward_calls=0
    def __getattr__(self,name):return getattr(self.env,name)
    def step(self,actions,remaining_ticks=None):
        import time
        raw=self.env.step(actions) if remaining_ticks is None else self.env.step(actions,remaining_ticks)
        start=time.perf_counter();raw=self.reward.apply(raw);self.reward_seconds+=time.perf_counter()-start;self.reward_calls+=1;return raw
    def scene(self,kind):self.env.scene(kind);self.reward=PotentialReward(self.cfg,self.env.observe())
    def set_scene(self,i,kind):self.env.set_scene(i,kind);self.reward=PotentialReward(self.cfg,self.env.observe())
    def reset_one(self,i):self.env.reset_one(i);self.reward=PotentialReward(self.cfg,self.env.observe())
    def inject(self,i,state):self.env.inject(i,state);self.reward=PotentialReward(self.cfg,self.env.observe())
