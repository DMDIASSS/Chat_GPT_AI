"""Single-process reference PPO for replay scenario curricula.

This is NOT the native 100k tick/s trainer. It is a correct, inspectable
research baseline for two-phase clips and a strict teacher anchor. It does
not promote any checkpoint. Run from the root of DMDIASSS/Chat_GPT_AI.

Example:
python -m slater_research.train_scenarios --clips data/replay_scenarios \
  --phase shooter --episodes 12 --epochs 2 --out data/isolated/shooter01.pt
"""
from __future__ import annotations
import argparse
from pathlib import Path
import random
import sys
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

from slater_research.checkpoint import cycle9_pair, guarded_ppo_loss,save_candidate_atomic
from slater_research.replay_engine import Clip,TwoPhaseScenario,split_replay,counterfactual_goal_check


class MaskedValue(nn.Module):
    """Variable token count; ball always picked by its semantic IS_BALL bit."""
    def __init__(self):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(80,192),nn.Tanh(),nn.Linear(192,192),
                               nn.Tanh(),nn.Linear(192,1))

    def forward(self,q,kv,mask):
        # Nexto convention: a value of 1 masks an entity out.
        valid=(1-mask).unsqueeze(-1).clamp(0,1)
        mean=(kv*valid).sum(dim=1)/valid.sum(dim=1).clamp_min(1)
        ball_idx=torch.argmax(kv[:,:,3],dim=1)
        ball=kv[torch.arange(kv.size(0),device=kv.device),ball_idx]
        return self.net(torch.cat((q[:,0],mean,ball),dim=-1)).squeeze(-1)


def actor_logits(actor,q,kv,mask):
    result,_=actor((q,kv,mask))
    if result.shape[-1]!=90:raise RuntimeError(f'Unexpected Nexto action count {result.shape}')
    return result


def gae(reward,value,gamma=.995,lam=.95):
    advantage=np.zeros(len(reward),dtype=np.float32)
    acc=0.
    for t in range(len(reward)-1,-1,-1):
        next_value=value[t+1] if t+1<len(value) else 0.
        delta=reward[t]+gamma*next_value-value[t]
        acc=delta+gamma*lam*acc
        advantage[t]=acc
    return advantage,advantage+np.asarray(value,dtype=np.float32)


def collect_episode(clip,phase,actor,critic,seed,defenders=None):
    from rlgym.rocket_league.sim import RocketSimEngine
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    rng=np.random.default_rng(seed)
    engine=RocketSimEngine(rlbot_delay=False)
    episode={}
    try:
        scene=TwoPhaseScenario(clip,engine,phase,defenders=defenders)
        # Sparse restarts close to and far before a goal.
        goal=min(scene.horizon,clip.goal_step)
        candidates=[max(0,goal-int(s*120/8)) for s in (.5,2.,4.,8.,12.)]
        starts=[a for a in candidates if a<scene.horizon]
        scene.reset(start_step=int(rng.choice(starts)))
        observer=TeamObserver()
        previous={}
        trajectory={a:[] for a in scene.learners}
        lookup=nexto_actions()
        while True:
            views=observer.observe(scene.state,previous)
            controls={}
            decisions={}
            for aid in scene.learners:
                q,kv,mask=views[aid]
                q=torch.from_numpy(q[None]).float()
                kv=torch.from_numpy(kv[None]).float()
                mask=torch.from_numpy(mask[None]).float()
                with torch.no_grad():
                    logits=actor_logits(actor,q,kv,mask)
                    dist=Categorical(logits=logits)
                    act=dist.sample()
                    lp=float(dist.log_prob(act).item())
                    value=float(critic(q,kv,mask).item())
                idx=int(act.item())
                controls[aid]=np.asarray(lookup[idx],dtype=np.float32)
                decisions[aid]=(q[0],kv[0],mask[0],idx,lp,value)
            _,rewards,done,info=scene.step(controls)
            for aid in scene.learners:
                q,k,m,idx,lp,value=decisions[aid]
                trajectory[aid].append((q,k,m,idx,lp,value,float(rewards[aid])))
            previous=controls
            if done:break
        for aid,transitions in trajectory.items():
            if not transitions:continue
            values=[x[5] for x in transitions]
            rew=[x[6] for x in transitions]
            adv,ret=gae(rew,values)
            episode[aid]=[(x[0],x[1],x[2],x[3],x[4],float(a),float(r))
                          for x,a,r in zip(transitions,adv,ret)]
        return episode,info
    finally:
        engine.close()


def update(actor,teacher,critic,actor_opt,critic_opt,rows,epochs=2,batch=256,
           anchor=.08,clip=.15,device='cpu'):
    rng=np.random.default_rng(17)
    qs=torch.stack([r[0] for r in rows]).to(device)
    kv=torch.stack([r[1] for r in rows]).to(device)
    masks=torch.stack([r[2] for r in rows]).to(device)
    acts=torch.tensor([r[3] for r in rows],dtype=torch.long,device=device)
    old=torch.tensor([r[4] for r in rows],dtype=torch.float32,device=device)
    adv=torch.tensor([r[5] for r in rows],dtype=torch.float32,device=device)
    ret=torch.tensor([r[6] for r in rows],dtype=torch.float32,device=device)
    adv=(adv-adv.mean())/(adv.std(unbiased=False)+1.e-7)
    diagnostics=[]
    for epoch in range(epochs):
        for inds in np.array_split(rng.permutation(len(rows)),max(1,int(np.ceil(len(rows)/batch)))):
            indices=torch.as_tensor(inds,device=device)
            q,k,m=qs[indices],kv[indices],masks[indices]
            logits=actor_logits(actor,q,k,m)
            with torch.no_grad():ref=actor_logits(teacher,q,k,m)
            policy_loss=guarded_ppo_loss(logits,ref,acts[indices],old[indices],adv[indices],
                                         clip=clip,teacher_weight=anchor)
            if not torch.isfinite(policy_loss):raise FloatingPointError('Nonfinite policy loss')
            actor_opt.zero_grad(set_to_none=True)
            policy_loss.backward()
            torch.nn.utils.clip_grad_norm_(actor.parameters(),.5)
            actor_opt.step()
            value_loss=F.smooth_l1_loss(critic(q,k,m),ret[indices])
            critic_opt.zero_grad(set_to_none=True)
            value_loss.backward()
            torch.nn.utils.clip_grad_norm_(critic.parameters(),.5)
            critic_opt.step()
            diagnostics.append((float(policy_loss.detach()),float(value_loss.detach())))
    return {'policy_loss':float(np.mean([x[0] for x in diagnostics])),
            'value_loss':float(np.mean([x[1] for x in diagnostics])),
            'n_decisions':len(rows)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--project-root',default='.')
    p.add_argument('--clips',required=True)
    p.add_argument('--phase',choices=('shooter','defender'),required=True)
    p.add_argument('--episodes',type=int,default=8)
    p.add_argument('--epochs',type=int,default=2)
    p.add_argument('--out',required=True)
    p.add_argument('--lr',type=float,default=3.e-6)
    p.add_argument('--seed',type=int,default=1337)
    p.add_argument('--max-shot-error',type=float,default=250.)
    args=p.parse_args()
    if args.episodes<1 or args.epochs<1:raise ValueError('positive episodes and epochs required')
    torch.manual_seed(args.seed);random.seed(args.seed)
    torch.set_num_threads(1)
    # Reject an empty dataset BEFORE loading the expensive checkpoint/model.
    # Zero clips must not be interpreted as a successful training run.
    pool=[]
    for path in sorted(Path(args.clips).glob('*.npz')):
        c=Clip.load(path)
        if split_replay(c.replay_sha)!='train':continue
        if args.phase=='defender':
            fidelity=counterfactual_goal_check(c,max_shot_position_error=args.max_shot_error)
            print(f'FIDELITY {path.name}: {fidelity}',flush=True)
            if not fidelity['accepted']:continue
        pool.append((path,c))
    if not pool:raise ValueError('No train-split, fidelity-accepted clips found. Stop and investigate replay controls.')
    actor,teacher=cycle9_pair(args.project_root)
    critic=MaskedValue()
    ao=torch.optim.Adam(actor.parameters(),lr=args.lr)
    co=torch.optim.Adam(critic.parameters(),lr=2.e-4)
    observations=[]
    for episode_idx in range(args.episodes):
        path,clip=pool[episode_idx%len(pool)]
        batch,info=collect_episode(clip,args.phase,actor,critic,args.seed+episode_idx)
        for rows in batch.values():observations.extend(rows)
        print(f'episode {episode_idx+1}/{args.episodes}: {path.name}, decisions={len(observations)}, {info}',flush=True)
    metrics=update(actor,teacher,critic,ao,co,observations,epochs=args.epochs)
    save_candidate_atomic(args.out,actor,critic,ao,
                          {'phase':args.phase,'metrics':metrics,'seed':args.seed,
                           'source':'Cycle9 SHA-verified; not ready for promotion'})
    print('SAVED isolated PPO candidate:',args.out,metrics)
    print('TRAINING DOES NOT PROVE SKILL: evaluate VS Cycle9, Nexto and held-out replays.')

if __name__=='__main__':main()
