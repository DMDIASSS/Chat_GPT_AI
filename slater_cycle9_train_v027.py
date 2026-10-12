r"""Slater v0.2.7 — isolated, RESUMABLE Cycle9 PPO vs frozen Nexto + frozen Cycle9.

Starts from original SHA-pinned Cycle9 by default; no replay data is used here.
Balance player side per training episode and evaluate both sides vs the ACTUAL
unmodified vendor Nexto policy on paired kickoff seeds. Periodic checkpoints.

Initial run:
  .venv\Scripts\python.exe slater_cycle9_train_v027.py --updates 60 --rollout-steps 1024 --checkpoint-every 20 --run slater_v027_run01
Resume in a NEW run (source files remain frozen):
  .venv\Scripts\python.exe slater_cycle9_train_v027.py --resume data/isolated/slater_v027_run01_u0060.pt --updates 60 --rollout-steps 1024 --checkpoint-every 20 --run slater_v027_run02

This is a 1v1 training stage; not replay curriculum or teamplay, and not a full-match Nexto 90%-win-rate benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired

EXPECTED_NEXTO_SHA = paired.EXPECTED_NEXTO_SHA256


def safe_run(run: str) -> str:
    if not run or len(run)>80 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in run):
        raise ValueError('Use simple run name, letters/digits/underscore/dash only (max 80 chars)')
    return run


def validate_resume(path: str, root: Path):
    p = Path(path).resolve()
    isolated = (root/'data'/'isolated').resolve()
    if not p.is_relative_to(isolated) or not p.is_file() or p.suffix != '.pt':
        raise ValueError('Resume checkpoint must be an existing .pt under data/isolated')
    return p


class SideBalanced1v1(base.Native1v1):
    """Student can be Blue or Orange. Frozen opponent alternates Cycle9/Nexto.

    Win signal and progress are ALWAYS from the student perspective.
    Does not modify arena coordinate conventions or any observer internals.
    """
    def __init__(self, actions, observer, opponents, max_steps, device):
        super().__init__(actions, observer, opponents[0], max_steps, device)
        self.opponents = tuple(opponents)
        self.student_side = 'blue'
        self.episode_count = 0
        self.current_opponent = 'cycle9'

    def reset(self, seed: int):
        super().reset(seed)
        # Deterministic alternation, independent of numeric seed parity.
        i = self.episode_count
        self.episode_count += 1
        self.student_side = 'blue' if i % 2 == 0 else 'orange'
        self.opponent = self.opponents[(i//2) % len(self.opponents)]
        self.current_opponent = 'cycle9' if (i//2) % len(self.opponents)==0 else 'nexto'
        side = 'blue-0' if self.student_side=='blue' else 'orange-0'
        self.obs = base.read_obs(self.state, self.previous, self.observer, side)
        return self.obs

    def step(self, student_action: int):
        blue_student = self.student_side == 'blue'
        sid = 'blue-0' if blue_student else 'orange-0'
        oid = 'orange-0' if blue_student else 'blue-0'
        sign = 1. if blue_student else -1.
        old_ball_y = float(self.state.ball.position[1])
        old_dist = float(np.linalg.norm(self.state.cars[sid].physics.position-self.state.ball.position))
        other_view = base.read_obs(self.state, self.previous, self.observer, oid)
        with torch.no_grad():
            a_opp = int(base.logits_of(self.opponent, base.to_tensors(other_view,self.device)).argmax(-1).item())
        student_control = np.array(self.actions[int(student_action)],dtype=np.float32,copy=True)
        other_control = np.array(self.actions[a_opp],dtype=np.float32,copy=True)
        commands = {sid: np.repeat(student_control[None],base.ACTION_REPEAT,axis=0),
                    oid: np.repeat(other_control[None],base.ACTION_REPEAT,axis=0)}
        self.state = self.engine.step(commands,{})
        self.previous = {sid:student_control, oid:other_control}
        self.t += 1
        car = self.state.cars[sid]
        ball = self.state.ball
        progress = float(np.clip(sign*(ball.position[1]-old_ball_y)/500., -.5,.5))
        closing = float(np.clip((old_dist-np.linalg.norm(car.physics.position-ball.position))/500., -.5,.5))
        stouches = int(car.ball_touches)
        otouches = int(self.state.cars[oid].ball_touches)
        self.touches += stouches
        self.opponent_touches += otouches
        goal = bool(self.state.goal_scored)
        outcome = int(sign*np.sign(ball.position[1])) if goal else 0
        reward = .20*progress + .07*closing + .35*stouches - .002 + 10.*outcome
        if not math.isfinite(reward):
            raise FloatingPointError('Nonfinite reward')
        self.total_reward += reward
        done = bool(goal or self.t >= self.max_steps)
        self.obs = base.read_obs(self.state, self.previous, self.observer, sid)
        return self.obs, float(reward), done, {
            'outcome':outcome, 'student_side':self.student_side, 'opponent':self.current_opponent,
            'student_touches':self.touches, 'opponent_touches':self.opponent_touches,
            'reward':self.total_reward, 'steps':self.t, 'ball_y':float(ball.position[1]),
            'timeout':bool(done and not goal),
        }


def evaluate_vs_nexto(student, cycle9, nexto, actions, observer, num_seeds, episode_steps, base_seed):
    """Compare Cycle9 and student directly vs frozen ORIGINAL Nexto on both sides."""
    blue = base.Native1v1(actions,observer,nexto,max_steps=episode_steps,device='cpu')
    orange = paired.RoleSwap1v1(actions,observer,nexto,max_steps=episode_steps,device='cpu')
    results=[]
    try:
        for i in range(num_seeds):
            seed = base_seed + 997*i
            for side,env in (('blue',blue),('orange',orange)):
                for name,actor in (('original',cycle9),('candidate',student)):
                    rec=paired.one_game(env,actor,seed,side)
                    rec['policy']=name
                    results.append(rec)
    finally:
        blue.close();orange.close()
    return {
        'seed_count':num_seeds, 'max_episode_steps':episode_steps,
        'original':paired.aggregate([r for r in results if r['policy']=='original']),
        'candidate':paired.aggregate([r for r in results if r['policy']=='candidate']),
        'paired':paired.comparison(results),
        'by_side':{pol:{side:paired.aggregate([r for r in results if r['policy']==pol and r['side']==side])
                        for side in ('blue','orange')} for pol in ('original','candidate')},
    }


def resume_checkpoint(actor, critic, actor_opt, critic_opt, resume: Path, source_sha: str):
    doc = torch.load(resume, map_location='cpu',weights_only=True)
    if doc.get('source_sha')!=source_sha or doc.get('stage')!='slater_v027' or not isinstance(doc.get('actor'),dict):
        raise ValueError('Refusing non-v027 or non-Cycle9 checkpoint')
    actor.load_state_dict(doc['actor'],strict=True)
    critic.load_state_dict(doc['critic'],strict=True)
    actor_opt.load_state_dict(doc['actor_optimizer'])
    critic_opt.load_state_dict(doc['critic_optimizer'])
    previous_updates = int(doc.get('global_updates',-1))
    if previous_updates <1:
        raise ValueError('Invalid previous update count')
    return previous_updates


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--resume',default=None)
    p.add_argument('--updates',type=int,default=60,help='Additional PPO updates in this run')
    p.add_argument('--rollout-steps',type=int,default=1024)
    p.add_argument('--checkpoint-every',type=int,default=20)
    p.add_argument('--max-episode-steps',type=int,default=450,help='450 decisions = 30 sec; not a full match')
    p.add_argument('--eval-seeds',type=int,default=8)
    p.add_argument('--eval-max-steps',type=int,default=450)
    p.add_argument('--epochs',type=int,default=2)
    p.add_argument('--minibatch',type=int,default=128)
    p.add_argument('--actor-lr',type=float,default=5e-6)
    p.add_argument('--critic-lr',type=float,default=2e-4)
    p.add_argument('--teacher-weight',type=float,default=.25)
    p.add_argument('--seed',type=int,default=20261011)
    args=p.parse_args()
    safe_run(args.run)
    if (min(args.updates,args.rollout_steps,args.checkpoint_every,args.max_episode_steps,args.eval_seeds,args.eval_max_steps,args.epochs,args.minibatch) < 1
            or args.eval_seeds>128 or args.max_episode_steps>4500 or args.eval_max_steps>4500
            or args.rollout_steps>65536 or args.minibatch>args.rollout_steps):
        p.error('Invalid counts or safety bounds')
    if not (0<args.actor_lr<=3e-5 and 0<args.critic_lr<=1e-3 and 0.05<=args.teacher_weight<=1):
        p.error('Learning-rate or teacher KL weight outside guardrail')
    root=Path.cwd().resolve()
    isolated=(root/'data'/'isolated').resolve()
    if args.resume:
        resume=validate_resume(args.resume,root)
    else: resume=None
    # Preflight: fail before training if ANY output for this run already exists.
    start_updates=0
    # Actual checkpoint indices depend on optional resume; run prefix is never reused.
    if any(isolated.glob(f'{args.run}_u*')):
        raise FileExistsError(f'Run prefix already exists: {args.run}')
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA,cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    source=root/CYCLE9; nexto_path=root/'vendor'/'nexto'/'nexto-model.pt'
    sha=base.sha256(source)
    nexto_sha=base.sha256(nexto_path)
    if sha!=CYCLE9_SHA or nexto_sha!=EXPECTED_NEXTO_SHA:
        raise RuntimeError('Protected source or Nexto checksum mismatch')
    actor,cycle9=cycle9_pair(root)
    actor.eval();cycle9.eval()
    for param in cycle9.parameters():param.requires_grad_(False)
    nexto=torch.jit.load(str(nexto_path),map_location='cpu')
    nexto.eval()
    for param in nexto.parameters():param.requires_grad_(False)
    if any(p.data_ptr()==q.data_ptr() for p,q in zip(actor.parameters(),cycle9.parameters())):
        raise RuntimeError('Student and protected teacher share storage')
    native_actions=nexto_actions()
    actions=np.stack([np.asarray(native_actions[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape!=(90,8) or not np.isfinite(actions).all():raise RuntimeError('Bad action lookup')
    critic=base.ValueNet()
    actor_opt=torch.optim.Adam(actor.parameters(),lr=args.actor_lr)
    critic_opt=torch.optim.Adam(critic.parameters(),lr=args.critic_lr)
    if resume is not None:
        start_updates=resume_checkpoint(actor,critic,actor_opt,critic_opt,resume,sha)
    observer=TeamObserver()
    print('TRAIN_REAL_CYCLE9 1v1 against frozen NEXTO and CYCLE9; side balanced; independent new policy',flush=True)
    print('GUARDS CYCLE9',sha,'NEXTO',nexto_sha,'RESUME',str(resume),'START_UPDATES',start_updates,flush=True)
    print('ARGS',json.dumps(vars(args),sort_keys=True),flush=True)
    before=evaluate_vs_nexto(actor,cycle9,nexto,actions,observer,args.eval_seeds,args.eval_max_steps,args.seed+500000)
    print('START_VS_REAL_NEXTO',json.dumps(before,sort_keys=True),flush=True)
    t0=time.perf_counter()
    teacher_initial=[q.detach().clone() for q in cycle9.parameters()]
    nexto_initial=[q.detach().clone() for q in nexto.parameters()]
    env=SideBalanced1v1(actions,observer,(cycle9,nexto),max_steps=args.max_episode_steps,device='cpu')
    logs=[]
    try:
        for i in range(args.updates):
            global_update=start_updates+i+1
            data,ends=base.collect(actor,critic,env,args.rollout_steps,args.seed+global_update*1373,'cpu')
            info=base.update(actor,cycle9,critic,actor_opt,critic_opt,data,args.epochs,args.minibatch,
                             args.teacher_weight,args.seed+global_update,'cpu')
            info.update(update=global_update,steps=args.rollout_steps,finished_episodes=len(ends),
                        wins=sum(x['outcome']==1 for x in ends),losses=sum(x['outcome']==-1 for x in ends),
                        touches=sum(x['student_touches'] for x in ends),
                        orange_episodes=sum(x['student_side']=='orange' for x in ends),
                        nexto_episodes=sum(x['opponent']=='nexto' for x in ends))
            print('UPDATE',json.dumps(info,sort_keys=True),flush=True)
            logs.append(info)
            if global_update % args.checkpoint_every==0 or i+1==args.updates:
                # Check fixed model parameters, source bytes, and no prior outputs.
                if base.sha256(source)!=sha or base.sha256(nexto_path)!=nexto_sha:raise RuntimeError('Protected disk source hash changed')
                if any(not torch.equal(q,z) for q,z in zip(cycle9.parameters(),teacher_initial)) or any(not torch.equal(q,z) for q,z in zip(nexto.parameters(),nexto_initial)):
                    raise RuntimeError('Frozen model changed')
                comparison=evaluate_vs_nexto(actor,cycle9,nexto,actions,observer,
                                            args.eval_seeds,args.eval_max_steps,args.seed+500000)
                print('EVAL_VS_REAL_NEXTO',global_update,json.dumps(comparison,sort_keys=True),flush=True)
                cp=isolated/f'{args.run}_u{global_update:04d}.pt'
                rp=isolated/f'{args.run}_u{global_update:04d}.json'
                base.check_output(cp,root)
                base.check_output(rp,root,'.json')
                metadata={'stage':'slater_v027','source_sha':sha,'nexto_sha':nexto_sha,
                          'global_updates':global_update,'run':args.run,'resume':str(resume) if resume else None,
                          'args':vars(args),'baseline_eval':before,'evaluation':comparison,
                          'recent_update_stats':logs[-args.checkpoint_every:],
                          'total_run_decisions':(i+1)*args.rollout_steps,
                          'warning':'1v1 PPO; no replays/teamplay/full-length benchmark; NOT promoted'}
                payload={'stage':'slater_v027','source_sha':sha,'global_updates':global_update,
                         'actor':actor.state_dict(),'critic':critic.state_dict(),
                         'actor_optimizer':actor_opt.state_dict(),'critic_optimizer':critic_opt.state_dict(),
                         'meta':metadata}
                base.save_create_only(cp,payload)
                rp.parent.mkdir(parents=True,exist_ok=True)
                with rp.open('x',encoding='utf-8') as f:json.dump(metadata,f,indent=2)
                print('SAVED_ISOLATED',cp,'SHA256',base.sha256(cp),flush=True)
    finally:
        env.close()
    print('SUMMARY',json.dumps({'completed_updates':args.updates,'global_updates':start_updates+args.updates,
                                 'train_decisions':args.updates*args.rollout_steps,
                                 'training_seconds':round(time.perf_counter()-t0,3),
                                 'last_eval_vs_nexto':comparison,
                                 'original_cycle9_unchanged':base.sha256(source)==sha,
                                 'original_nexto_unchanged':base.sha256(nexto_path)==nexto_sha},sort_keys=True),flush=True)
    print('NO_PROMOTION_NO_REPLAY_TOUCH_CYCLE9_AND_NEXTO_UNCHANGED',flush=True)

if __name__=='__main__':
    main()
