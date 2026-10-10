"""Isolated native Nexto multi-car RocketSim research; explicitly NOT an autopromotion path.

Supports shared-policy teammate control for 1v2, 1v3, 2v1, 2v2, 2v3, 3v1,
3v2, 3v3. No public online gameplay. Rewards focus on team scoring, not touches/demos.
Dependencies already present in Chat_GPT_AI: rlgym v2, RocketSim, native_nexto,
nexto_teacher, torch. This new mode is separate from AutoLeague.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

ROOT=Path(__file__).resolve().parent
# Checkpoint can be overridden explicitly, but output must always remain under team_research
DEFAULT=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
OUTPUT=ROOT/'data'/'afk_improved'/'team_research'
ACTION_TICKS=8
MAX_PLAYERS=6

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for x in iter(lambda:f.read(1048576),b''): h.update(x)
 return h.hexdigest()

def validate_teams(ours,them):
 if not 1<=ours<=3 or not 1<=them<=3: raise ValueError('Team sizes must both be between 1 and 3')
 if ours+them>MAX_PLAYERS: raise ValueError('Too many cars for Nexto attention observation')
 return f'{ours}v{them}'

def encode_multi(state):
 """Preserve exact Nexto legacy flattened layout, generalized to 2–6 players."""
 from nexto_teacher import _car_block,INV
 cars=sorted(state.cars.items(),key=lambda t:(bool(t[1].is_orange),str(t[0])))
 if len(cars)<2 or len(cars)>6: raise ValueError('2..6 cars required')
 pads=np.asarray(state.boost_pad_timers,dtype=np.float32).reshape(-1)
 if pads.shape!=(34,): raise ValueError('34 boost pads required')
 ball=state.ball
 p=np.asarray(ball.position,dtype=np.float64)
 v=np.asarray(ball.linear_velocity,dtype=np.float64)
 w=np.asarray(ball.angular_velocity,dtype=np.float64)
 encoded=[0.,0.,0.,*((pads<=1e-6).astype(float).tolist()),*p,*v,*w,*(p*INV),*(v*INV),*(w*INV)]
 for idx,(_,car) in enumerate(cars):encoded.extend(_car_block(car,idx))
 enc=np.asarray(encoded,dtype=np.float64)
 if enc.shape!=(55+38*len(cars),) or not np.isfinite(enc).all():
  raise ValueError(f'Invalid observation encoded shape {enc.shape}')
 return enc,[a for a,_ in cars]

class TeamObserver:
 def __init__(self):
  from vendor.nexto.nexto_obs import NextoObsBuilder
  self.builder=NextoObsBuilder(n_players=6,tick_skip=ACTION_TICKS)
 def observe(self,state,prev):
  enc,ids=encode_multi(state)
  obs=self.builder.batched_build_obs(enc[None,:])
  result={}
  for i,aid in enumerate(ids):
   self.builder.add_actions(obs,np.asarray(prev.get(aid,np.zeros(8)),dtype=np.float64),i)
   q,kv,mask=obs[i]
   q=q[0].astype(np.float32);kv=kv[0].astype(np.float32);mask=mask[0].astype(np.float32)
   if q.shape!=(1,32) or kv.shape!=(41,24) or mask.shape!=(41,):raise ValueError('Unexpected padded Nexto features')
   result[aid]=(q,kv,mask)
  return result

class TeamMatch:
 def __init__(self,engine,observer,ours,them,orange=False,scenario='kickoff',seed=0):
  self.engine=engine;self.observer=observer;self.ours_size=ours;self.them_size=them
  self.orange=bool(orange);self.scenario=scenario;self.seed=seed;self.reset_count=0
  self.reset()
 def reset(self):
  from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
  base=self.engine.create_base_state()
  blue=self.them_size if self.orange else self.ours_size
  orange=self.ours_size if self.orange else self.them_size
  FixedTeamSizeMutator(blue_size=blue,orange_size=orange).apply(base,{})
  # 'grounded' is supported by the existing curriculum, but randomized positions
  # must still be validated in the real installed version of RocketSim.
  if self.scenario=='grounded':
   from chatgpt_ai.curriculum import ChatGPTCurriculum
   ChatGPTCurriculum('grounded').apply(base,{})
  else:KickoffMutator().apply(base,{})
  if self.scenario=='pressure':self.set_defensive_pressure(base)
  self.reset_count+=1
  self.state=self.engine.set_state(base,{})
  self.our_ids=sorted([a for a,c in self.state.cars.items() if bool(c.is_orange)==self.orange],key=str)
  self.their_ids=sorted([a for a,c in self.state.cars.items() if bool(c.is_orange)!=self.orange],key=str)
  if len(self.our_ids)!=self.ours_size or len(self.their_ids)!=self.them_size:raise RuntimeError('Car count mismatch')
  self.prev={};self.decisions=0
  return self.observer.observe(self.state,self.prev)
 def set_defensive_pressure(self,state):
  """Controlled defensive starts: ball threatens learner's goal. No arbitrary exploit rewards."""
  from mechanics_scenarios import basis
  rng=np.random.default_rng(self.seed+self.reset_count*7919)
  own_sign=1. if self.orange else -1.
  offset=float(rng.uniform(-700.,700.))
  state.ball.position=np.array([offset,own_sign*float(rng.uniform(2500.,3400.)),110.])
  state.ball.linear_velocity=np.array([float(rng.uniform(-240.,240.)),own_sign*float(rng.uniform(700.,1300.)),0.])
  state.ball.angular_velocity=np.zeros(3)
  ours=[c for _,c in state.cars.items() if bool(c.is_orange)==self.orange]
  theirs=[c for _,c in state.cars.items() if bool(c.is_orange)!=self.orange]
  for side,cars,yval in [(True,ours,own_sign*4050.),(False,theirs,own_sign*1550.)]:
   for j,car in enumerate(cars):
    x=(j-(len(cars)-1)/2.)*1300.+float(rng.uniform(-140.,140.))
    car.physics.position=np.array([x,yval+float(rng.uniform(-200.,200.)),17.])
    look_dir=np.array([-x*.0002,(-own_sign if side else own_sign),0.])
    car.physics.rotation_mtx=basis(look_dir,up=(0,0,1))
    car.physics.linear_velocity=np.zeros(3)
    car.physics.angular_velocity=np.zeros(3)
    car.boost_amount=float(rng.uniform(20.,55.))
    car.on_ground=True

 def step(self,actions,max_decisions):
  from nexto_teacher import nexto_actions
  if set(actions)!=set(self.our_ids+self.their_ids):raise ValueError('Missing car action')
  table=nexto_actions()
  old_ball=float(self.state.ball.position[1]);old_pos={a:np.asarray(c.physics.position).copy() for a,c in self.state.cars.items()}
  controls={a:np.asarray(table[int(v)],dtype=np.float32) for a,v in actions.items()}
  self.state=self.engine.step({a:np.tile(ctrl,(ACTION_TICKS,1)) for a,ctrl in controls.items()}, {})
  self.prev=controls;self.decisions+=1
  goal=bool(getattr(self.state,'goal_scored',False))
  sign=-1 if self.orange else 1
  net=sign*float(self.state.ball.position[1]);prev_net=sign*old_ball
  # Potential-shaped reward bounded. Goal is the dominant objective.
  progress=float(np.clip((net-0.995*prev_net)/6000.,-0.08,0.08))*0.05
  who='ours' if (float(self.state.ball.position[1])>0)!=self.orange else 'them'
  goal_reward=(10 if who=='ours' else -10) if goal else 0.
  shared=progress+goal_reward-0.0003
  ball=np.asarray(self.state.ball.position)
  personal={}
  for aid in self.our_ids:
   a=old_pos[aid];b=np.asarray(self.state.cars[aid].physics.position)
   # Tiny discounted potential; do NOT reward raw ball hits or demos.
   before=np.linalg.norm(a-ball);after=np.linalg.norm(b-ball)
   personal[aid]=shared+float(np.clip((before-0.995*after)/6000.,-.1,.1))*0.02
  done=goal or self.decisions>=max_decisions
  return personal,done,(who if goal else 'draw')

class TeamCritic(nn.Module):
 def __init__(self):
  super().__init__();self.net=nn.Sequential(nn.Linear(32+24+24,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh(),nn.Linear(128,1))
 def forward(self,q,kv,mask):
  legal=(1-mask).unsqueeze(-1).clamp(0,1)
  mean=(kv*legal).sum(dim=1)/legal.sum(dim=1).clamp_min(1)
  return self.net(torch.cat([q[:,0],mean,kv[:,6]],dim=-1)).squeeze(-1)

def tensors(x):
 q,k,m=x
 return (torch.from_numpy(q[None]).float(),torch.from_numpy(k[None]).float(),torch.from_numpy(m[None]).float())

def action(actor,obs,stochastic=False):
 from native_nexto import actor_logits
 q,k,m=tensors(obs)
 with torch.no_grad():
  logits=actor_logits(actor,q,k,m)
  dist=Categorical(logits=logits)
  act=dist.sample() if stochastic else logits.argmax(-1)
 return int(act.item()),float(dist.log_prob(act).item())

def load_actor(path):
 from auto_league import actor_from
 return actor_from(Path(path),'cpu')

def save(path,actor,critic,optim,critoptim,info):
 from auto_league import atomic_json
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.pt.partial')
 if path.exists(): raise FileExistsError('Refusing to overwrite saved experiment')
 torch.save({'actor':{k:v.detach().cpu().clone() for k,v in actor.state_dict().items()},
             'critic':critic.state_dict(),'actor_optimizer':optim.state_dict(),'critic_optimizer':critoptim.state_dict(),**info},tmp)
 os.replace(tmp,path)
 atomic_json(path.with_suffix('.json'),info)

@contextlib.contextmanager
def exclusive_team():
 """Prevent simultaneous team experiments and accidental checkpoint races."""
 OUTPUT.mkdir(parents=True,exist_ok=True)
 lock=OUTPUT/'.team_research.lock'
 with lock.open('a+b') as f:
  f.seek(0);f.write(b'0');f.flush();f.seek(0)
  if os.name=='nt':
   import msvcrt
   try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
   except OSError as e:raise RuntimeError('Another Team Research process is active') from e
  else:
   import fcntl
   try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError as e:raise RuntimeError('Another Team Research process is active') from e
  try:yield
  finally:
   f.seek(0)
   if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def preflight(args):
 from nexto_teacher import NextoTeacher
 from rlgym.rocket_league.sim import RocketSimEngine
 from auto_league import actor_from
 validate_teams(args.ours,args.them)
 if not Path(args.source).is_file():raise FileNotFoundError(f'Need native checkpoint: {args.source}')
 actor=actor_from(Path(args.source),'cpu')
 engine=RocketSimEngine(rlbot_delay=False)
 try:
  match=TeamMatch(engine,TeamObserver(),args.ours,args.them,scenario=args.scenario,seed=args.seed)
  obs=match.observer.observe(match.state,match.prev)
  a=action(actor,obs[match.our_ids[0]])[0]
  assert 0<=a<90
  print(f'PASS: real RocketSim {validate_teams(args.ours,args.them)} state, padded observation, native actor and action')
 finally:engine.close()

def run(args):
 from rlgym.rocket_league.sim import RocketSimEngine
 from native_nexto import actor_logits,discounted_gae
 from auto_league import actor_from
 validate_teams(args.ours,args.them)
 if any(k<1 for k in [args.steps,args.rollout,args.epochs,args.minibatch,args.episode_decisions]):raise ValueError('All counts must be >0')
 if args.lr<=0 or args.lr>1e-3:raise ValueError('Refusing dangerous learning rate')
 source=Path(args.source).resolve();hash_source=sha(source)
 branch=OUTPUT/(f'{args.ours}v{args.them}_{args.scenario}_s{args.seed}_lr{args.lr:.0e}')
 result=branch/'candidate.pt'
 if result.exists():raise FileExistsError('Experiment already exists; select another seed or keep result. '+str(result))
 branch.mkdir(parents=True,exist_ok=True)
 random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed);torch.set_num_threads(2)
 learner=load_actor(source);anchor=load_actor(source);original=load_actor(source)
 anchor.eval();original.eval()
 for p in anchor.parameters():p.requires_grad_(False)
 critic=TeamCritic();optim=torch.optim.Adam(learner.parameters(),lr=args.lr);critoptim=torch.optim.Adam(critic.parameters(),lr=2e-4)
 engine=RocketSimEngine(rlbot_delay=False)
 observer=TeamObserver()
 rng=random.Random(args.seed)
 records=Counter();steps=0
 try:
  match=TeamMatch(engine,observer,args.ours,args.them,orange=False,scenario=args.scenario,seed=args.seed)
  while steps<args.steps:
   trajectories={i:[] for i in range(args.ours)}
   horizon=min(args.rollout,(args.steps-steps+args.ours-1)//args.ours)
   for _ in range(horizon):
    observations=observer.observe(match.state,match.prev)
    actions={}
    for aid in match.their_ids:actions[aid]=action(original,observations[aid])[0]
    for i,aid in enumerate(match.our_ids):
     obs=observations[aid];act,logp=action(learner,obs,stochastic=True)
     with torch.no_grad(): val=float(critic(*tensors(obs)).item())
     trajectories[i].append([obs,act,logp,val,None,None])
     actions[aid]=act
    reward,done,winner=match.step(actions,args.episode_decisions)
    for i,aid in enumerate(match.our_ids):
     trajectories[i][-1][-2:]=[float(reward[aid]),done]
    if done:
     records[winner]+=1
     match.orange=bool(rng.randrange(2));match.reset()
   batch=[]
   for i,traj in trajectories.items():
    if traj[-1][-1]:bootstrap=0.
    else:
     obs=observer.observe(match.state,match.prev)[match.our_ids[i]]
     with torch.no_grad():bootstrap=float(critic(*tensors(obs)).item())
    gae,ret=discounted_gae([t[4] for t in traj],[t[3] for t in traj],[t[5] for t in traj],bootstrap)
    for t,g,r in zip(traj,gae,ret):batch.append((t[0],t[1],t[2],g,r))
   q=torch.from_numpy(np.stack([r[0][0] for r in batch])).float();kv=torch.from_numpy(np.stack([r[0][1] for r in batch])).float()
   masks=torch.from_numpy(np.stack([r[0][2] for r in batch])).float();acts=torch.tensor([r[1] for r in batch],dtype=torch.long)
   old=torch.tensor([r[2] for r in batch]).float();adv=torch.tensor([r[3] for r in batch]).float();rets=torch.tensor([r[4] for r in batch]).float()
   adv=(adv-adv.mean())/(adv.std(unbiased=False)+1e-6)
   for _ in range(args.epochs):
    for ids in torch.randperm(len(batch)).split(args.minibatch):
     logits=actor_logits(learner,q[ids],kv[ids],masks[ids]);dist=Categorical(logits=logits)
     ratio=torch.exp(dist.log_prob(acts[ids])-old[ids]);surrogate=torch.minimum(ratio*adv[ids],ratio.clamp(.85,1.15)*adv[ids]).mean()
     with torch.no_grad():ref=actor_logits(anchor,q[ids],kv[ids],masks[ids])
     kl=F.kl_div(F.log_softmax(logits,-1),F.softmax(ref,-1),reduction='batchmean')
     loss=-surrogate+.04*kl-.001*dist.entropy().mean()
     if not torch.isfinite(loss):raise FloatingPointError('Actor PPO loss nonfinite; no checkpoint written')
     optim.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(learner.parameters(),1.0);optim.step()
     value=critic(q[ids],kv[ids],masks[ids]);vloss=F.mse_loss(value,rets[ids]);
     if not torch.isfinite(vloss):raise FloatingPointError('Critic loss nonfinite; no checkpoint written')
     critoptim.zero_grad();vloss.backward();torch.nn.utils.clip_grad_norm_(critic.parameters(),1.0);critoptim.step()
   steps+=horizon*args.ours
   print(f'[TEAM {args.ours}v{args.them}] controlled samples {steps}/{args.steps}; matches {sum(records.values())}; W/L/D {records["ours"]}/{records["them"]}/{records["draw"]}',flush=True)
  if sha(source)!=hash_source: raise RuntimeError('Baseline changed during training; refusing output')
  info={'source':str(source),'source_sha256':hash_source,'players':f'{args.ours}v{args.them}',
        'scenario':args.scenario,'controlled_samples':steps,'seed':args.seed,'actor_lr':args.lr,
        'results':dict(records),'saved_utc':datetime.now(timezone.utc).isoformat(),
        'promotion_allowed':False,'competitive_verified':False,
        'note':'Unverified experimental native actor; evaluate against source in full matches before use.'}
  save(result,learner,critic,optim,critoptim,info)
  print('Experimental checkpoint:',result)
 finally:engine.close()

def evaluate(args):
 """Paired held-out kickoff/grounded short episodes; does not auto promote."""
 from rlgym.rocket_league.sim import RocketSimEngine
 from auto_league import atomic_json
 validate_teams(args.ours,args.them)
 source=load_actor(Path(args.source));candidate=load_actor(Path(args.candidate))
 engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver()
 try:
  results={}
  for label,actor in [('source',source),('candidate',candidate)]:
   counts=Counter();unique=set();ticks=0
   for game in range(args.games):
    # Deterministic same seeds, team color, scenarios for both policies.
    random.seed(args.seed+game*997);np.random.seed((args.seed+game*997)%(2**32))
    scenario=args.scenario if args.scenario!='mixed' else (['kickoff','grounded','pressure'][game%3])
    match=TeamMatch(engine,observer,args.ours,args.them,orange=bool(game%2),scenario=scenario,seed=args.seed+game*997)
    positions=tuple(tuple(np.rint(np.asarray(car.physics.position)).astype(int)) for _,car in sorted(match.state.cars.items(),key=lambda t:str(t[0])))
    unique.add((tuple(np.rint(match.state.ball.position).astype(int)),positions))
    winner='draw'
    for step in range(args.episode_decisions):
     obs=observer.observe(match.state,match.prev)
     commands={aid:action(actor,obs[aid])[0] for aid in match.our_ids}
     commands.update({aid:action(source,obs[aid])[0] for aid in match.their_ids})
     reward,done,winner=match.step(commands,args.episode_decisions)
     if done:break
    ticks+=match.decisions
    counts[winner]+=1
   score=(counts['ours']+.5*counts['draw'])/args.games
   results[label]={'wins':counts['ours'],'losses':counts['them'],'draws':counts['draw'],'score':score,
                   'unique_starts':len(unique),'episodes':args.games,'decisions':ticks}
   print(label,results[label],flush=True)
  report={'player_mode':validate_teams(args.ours,args.them),'seed':args.seed,
          'source_sha256':sha(Path(args.source)),'candidate_sha256':sha(Path(args.candidate)),
          'results':results,'promoted':False,'competition_verified':False,
          'caveat':'Short first-goal episodes; do not treat as full-match proof. Both opponents frozen source actor.'}
  output=OUTPUT/'evaluations';output.mkdir(parents=True,exist_ok=True)
  file=output/f'{args.ours}v{args.them}_s{args.seed}_{sha(Path(args.candidate))[:12]}.json'
  if file.exists():raise FileExistsError('Evaluation already exists, change seed')
  atomic_json(file,report);print('Saved independent evaluation:',file)
 finally:engine.close()


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('command',choices=['preflight','train','evaluate'])
 p.add_argument('--source',type=Path,default=DEFAULT)
 p.add_argument('--candidate',type=Path,default=None)
 p.add_argument('--games',type=int,default=60)
 p.add_argument('--ours',type=int,default=1);p.add_argument('--them',type=int,default=2)
 p.add_argument('--scenario',choices=['kickoff','grounded','pressure','mixed'],default='kickoff')
 p.add_argument('--steps',type=int,default=512);p.add_argument('--rollout',type=int,default=128)
 p.add_argument('--epochs',type=int,default=2);p.add_argument('--minibatch',type=int,default=64)
 p.add_argument('--episode-decisions',type=int,default=150);p.add_argument('--lr',type=float,default=1.2e-5)
 p.add_argument('--seed',type=int,default=20261010)
 args=p.parse_args()
 if args.command=='preflight':preflight(args)
 elif args.command=='evaluate':
  if not args.candidate:raise ValueError('Supply --candidate for evaluation')
  if args.games<4:raise ValueError('Need at least 4 evaluation games')
  with exclusive_team():evaluate(args)
 elif args.scenario=='mixed':raise ValueError('Training supports kickoff/grounded/pressure; mixed only for evaluation')
 else:
  with exclusive_team():run(args)
if __name__=='__main__':main()
