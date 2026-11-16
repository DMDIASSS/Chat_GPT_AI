"""Bounded jump-to-contact rehabilitation, separate from confirmed ground bot."""
import numpy as np
from .acquisition import AcquisitionBatch,drill_states,reward_components

def air_states(rng,n):
    w=drill_states(rng,n)
    w[:,0,2]=rng.uniform(300,500,n);w[:,0,5]=rng.uniform(180,300,n)
    theta=rng.uniform(-np.pi,np.pi,n)
    for side in (0,1):
        angle=theta+side*np.pi
        distance=rng.uniform(180,420,n)
        car=w[:,side+1];car[:,:2]=w[:,0,:2]+np.column_stack([np.cos(angle),np.sin(angle)])*distance[:,None]
        yaw=angle+np.pi+rng.uniform(-.25,.25,n)
        car[:,9:12]=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(n)])
        car[:,3:6]=car[:,9:12]*rng.uniform(100,400,n)[:,None]
        car[:,15]=rng.uniform(60,100,n)
    return w

def elevated_hits(before,raw):
    high=np.maximum(before[:,0,2],raw['final_world'][:,0,2])>=220
    lifted=raw['final_world'][:,1:,2]>65
    return (raw['info'][:,1:3]>.5)&high[:,None]&lifted

class AirBatch(AcquisitionBatch):
    def __init__(self,env,cfg,seed):
        self.air=cfg['air_recovery'];super().__init__(env,cfg,seed)

    def _reset(self,indices):
        if not len(indices):return
        chosen=self.rng.random(len(indices))<self.air['fraction']
        self.drill[indices]=chosen;self.elapsed[indices]=0;self.seen[indices]=False
        ids=np.asarray(indices)[chosen]
        for i,w in zip(ids,air_states(self.rng,len(ids))):self.env.inject(int(i),w)
        self.raw=self.env.observe() # full native masks, including jump

    def step(self,actions,remaining_ticks=None):
        before=self.raw['world'];raw=self.env.step(actions) if remaining_ticks is None else self.env.step(actions,remaining_ticks)
        self.elapsed+=raw['info'][:,3]/120
        hits=elevated_hits(before,raw);success=hits.any(-1)
        custom=self.drill&(success|(self.elapsed>=self.air['seconds']))
        native_done=raw['terminated']|raw['truncated'];done=custom|native_done
        raw['terminated']|=custom;raw['truncated']&=~custom
        parts,new,metrics=reward_components(self.cfg,before,raw,self.elapsed,self.seen)
        ids=self.drill;world=raw['final_world'];delta=world[:,0:1,:3]-world[:,1:,:3]
        direction=delta/np.maximum(1,np.linalg.norm(delta,axis=-1,keepdims=True))
        toward=np.clip((world[:,1:,3:6]*direction).sum(-1)/2300,0,1)
        parts[ids,:,1]=self.air['approach_weight']*toward[ids]*(raw['info'][ids,3:4]/8)
        parts[ids,:,2]=(hits&~self.seen)[ids]*self.air['contact_bonus']
        parts[:,:,2]=np.where(parts[:,:,0]<0,0,parts[:,:,2])
        self.seen|=np.where(ids[:,None],hits,new)
        raw['reward_parts']=parts;raw['rewards']=parts.sum(-1)
        self.last={**metrics,'air_drill_fraction':float(ids.mean()),'high_contacts':int((hits&ids[:,None]).sum()),'completed_air_drills':int((done&ids).sum())}
        for i in np.flatnonzero(custom&~native_done):self.env.reset_one(int(i))
        if done.any():
            self._reset(np.flatnonzero(done))
            for key in ('world','pads','obs','mask'):raw[key]=self.raw[key]
        self.raw=raw;return raw
