"""Stationary-until-contact targets using RocketSim's native zero-velocity sleep.

Only episode setup injects state. No car/jump/control reset occurs during a trial.
"""
from collections import deque
import numpy as np
from .acquisition import AcquisitionBatch,reward_components
from .air_recovery import air_states,elevated_hits

LEVELS=((240,340,180,420),(300,450,250,650),(400,650,350,900))

def target_states(rng,n,level=0,released=False):
 z0,z1,d0,d1=LEVELS[level];w=air_states(rng,n)
 w[:,0,2]=rng.uniform(z0,z1,n);w[:,0,3:9]=0
 if released:
  w[:,0,3:5]=rng.uniform(-150,150,(n,2));w[:,0,5]=rng.uniform(300,450,n)
 angle=rng.uniform(-np.pi,np.pi,n)
 for side in (0,1):
  theta=angle+side*np.pi;distance=rng.uniform(d0,d1,n)
  car=w[:,side+1];car[:,:2]=w[:,0,:2]+np.column_stack([np.cos(theta),np.sin(theta)])*distance[:,None]
  yaw=theta+np.pi+rng.uniform(-.4,.4,n)
  car[:,9:12]=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(n)])
  car[:,3:6]=car[:,9:12]*rng.uniform(100,400,n)[:,None];car[:,15]=rng.uniform(60,100,n)
 return w

class HeldBallBatch(AcquisitionBatch):
 def __init__(self,env,cfg,seed,force=None):
  self.h=cfg['held_ball'];self.level=0;self.transfer=False;self.successes=deque(maxlen=128);self.force=force
  if self.h['version']!='stationary-air-v1' or self.h['seconds']!=4.:
   raise ValueError('Unknown stationary-air contract')
  if not .003<=self.h['drill_entropy']<=.03 or not 0<self.h['contact_bonus']<=1 or not 0<=self.h['approach_weight']<=.02:
   raise ValueError('Stationary-air reward/entropy bounds exceeded')
  if force not in (None,1,2):raise ValueError('Force only stationary or released drill scenes')
  self.tasks=np.zeros(len(env.observe()['world']),np.int8);self.levels=self.tasks.copy()
  self.learning_rows=np.ones((len(self.tasks),2),bool)
  # Fixed arena roles avoid short drills occupying almost no wall/decision time
  # compared with 90-second matches when tasks are sampled only at resets.
  order=np.random.default_rng(seed ^ 0x4E1D).permutation(len(self.tasks))
  normal=len(order)-round(.5*len(order));self.drill_order=order[normal:]
  super().__init__(env,cfg,seed)

 def curriculum_state(self):return {'level':self.level,'transfer':self.transfer,'successes':list(self.successes)}
 def restore_curriculum(self,state):
  if state['level'] not in range(3):raise ValueError('Invalid held curriculum level')
  self.level=state['level'];self.transfer=bool(state['transfer']);self.successes=deque(state['successes'],maxlen=128)
  for i in range(len(self.tasks)):self.env.reset_one(i)
  self._reset(np.arange(len(self.tasks)))

 def entropy_coefficients(self):
  weight=np.where(self.tasks>0,self.h['drill_entropy'],self.cfg['ppo']['entropy']).astype(np.float32)
  return np.repeat(weight[:,None],2,axis=1)

 def _reset(self,indices):
  if not len(indices):return
  assignment=np.zeros(len(self.tasks),np.int8);assignment[self.drill_order]=2
  count=min(len(self.drill_order),round((.15 if self.transfer else .35)*len(self.tasks)))
  assignment[self.drill_order[:count]]=1;tasks=assignment[indices].copy()
  if self.force is not None:tasks[:]=self.force
  self.tasks[indices]=tasks;self.drill[indices]=tasks>0
  self.elapsed[indices]=0;self.seen[indices]=False
  levels=np.where(self.rng.random(len(indices))<.2,0,self.level);self.levels[indices]=levels
  for task in (1,2):
   for level in range(3):
    ids=np.asarray(indices)[(tasks==task)&(levels==level)]
    for i,w in zip(ids,target_states(self.rng,len(ids),level,released=task==2)):self.env.inject(int(i),w)
  self.raw=self.env.observe()

 def step(self,actions,remaining_ticks=None):
  before=self.raw['world'];raw=self.env.step(actions) if remaining_ticks is None else self.env.step(actions,remaining_ticks)
  self.elapsed+=raw['info'][:,3]/120
  hits=elevated_hits(before,raw);success=hits.any(-1);learner_success=(hits&self.learning_rows).any(-1);valid=raw['info'][:,3]>0
  custom=(self.tasks>0)&valid&(success|(self.elapsed>=self.h['seconds']))
  native=raw['terminated']|raw['truncated'];done=native|custom
  raw['terminated']|=custom;raw['truncated']&=~custom
  parts=np.zeros_like(raw['reward_parts']);parts[:,:,0]=raw['reward_parts'][:,:,0]
  normal=self.tasks==0
  if normal.any():
   sub={k:raw[k][normal] for k in ('info','final_world','reward_parts','terminated')}
   base,new,_=reward_components(self.cfg,before[normal],sub,self.elapsed[normal],self.seen[normal])
   parts[normal]=base;self.seen[normal]|=new
  drill=self.tasks>0
  if drill.any():
   delta=before[:,0:1,:3]-before[:,1:,:3];unit=delta/np.maximum(1,np.linalg.norm(delta,axis=-1,keepdims=True))
   travel=((raw['final_world'][:,1:,:3]-before[:,1:,:3])*unit).sum(-1)
   parts[drill,:,1]=self.h['approach_weight']*np.clip(travel[drill]/(2300/15),-1,1)
   parts[drill,:,2]=(hits&~self.seen)[drill]*self.h['contact_bonus']
   parts[:,:,2]=np.where(parts[:,:,0]<0,0,parts[:,:,2]);self.seen[drill]|=hits[drill]
  raw['reward_parts']=parts;raw['rewards']=parts.sum(-1)
  for i in np.flatnonzero(done&(self.tasks==1)&(self.levels==self.level)):
   self.successes.append(bool(learner_success[i]))
  # A stochastic rollout success is not evidence the greedy exported actor
  # learned the task. Only the controller's frozen-policy probes advance level.
  self.last={'held_level':self.level,'transfer':self.transfer,'held_fraction':float((self.tasks==1).mean()),
     'released_fraction':float((self.tasks==2).mean()),'elevated_contacts':int((hits&drill[:,None]).sum()),
     'completed_held':int((done&(self.tasks==1)).sum()),'successful_held':int((done&(self.tasks==1)&learner_success).sum()),
     'completed_released':int((done&(self.tasks==2)).sum()),'successful_released':int((done&(self.tasks==2)&learner_success).sum())}
  for i in np.flatnonzero(custom&~native):self.env.reset_one(int(i))
  if done.any():
   self._reset(np.flatnonzero(done))
   for k in ('world','pads','obs','mask'):raw[k]=self.raw[k]
  self.raw=raw;return raw
