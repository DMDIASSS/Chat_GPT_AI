"""Slater v0.3.1: kickoff specialist PPO from u60 with replay starts + fake-kickoff opponents.

Not a guaranteed speedflip, fake-recognition classifier, or full-match improvement.
Evaluation reports first-touch / fake punish PROXIES from physical simulation.
Uses existing 90-action Nexto policy; a new macro-action model is necessary for
true speedflips (jump+yaw combinations excluded in current lookup table).

Train example:
 .venv\\Scripts\\python.exe slater_kickoff_train_v031.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --scenarios data/kickoffs_v031 --run kickoff_v031_a --updates 40 --rollout-steps 1024 --checkpoint-every 10
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
from slater_kickoff_extract_v031 import load_poses
from slater_cycle9_train_v027 import safe_run
from slater_cycle9_paired_eval_v026_fixed import EXPECTED_NEXTO_SHA256

# 50% trained full-policy opponents; 50% programmed fake-kickoff opponents.
MODES=('nexto','cycle9','nexto','idle_fake','turn_fake','late_fake')
FAKE_MODES=frozenset({'idle_fake','turn_fake','late_fake'})
EXPECTED_U60_SHA='5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74'


def fake_controls(mode, step, distance, base_control, *, side='orange'):
    """Scripted physical controls, NOT a teleported/ghost opponent."""
    a=np.asarray(base_control,dtype=np.float32).copy()
    if mode=='idle_fake':
        return np.zeros(8,dtype=np.float32)
    if mode=='turn_fake' and (step>=9 or distance<1650):
        # Abandon approach and turn to own corner. Distinguish sides reproducibly.
        return np.array([1.,1. if side=='orange' else -1.,0.,0.,0.,0.,0.,1.],dtype=np.float32)
    if mode=='late_fake' and distance<1000:
        # Fake a normal approach then cut boost and brake/handbrake sharply.
        return np.array([-1.,-1. if side=='orange' else 1.,0.,0.,0.,0.,0.,1.],dtype=np.float32)
    return a


def apply_pose(state, pose):
    """Preserve legal kickoff Car internal state from RLGym mutator; replace only pose."""
    if pose is None:return
    for side in ('blue','orange'):
        car=state.cars[side+'-0']
        car.physics.position=np.asarray(pose[side+'_position'],dtype=np.float32).copy()
        car.physics.euler_angles=np.asarray(pose[side+'_euler'],dtype=np.float32).copy()
        car.physics.linear_velocity=np.zeros(3,dtype=np.float32)
        car.physics.angular_velocity=np.zeros(3,dtype=np.float32)
        car.boost_amount=float(np.clip(pose[side+'_boost'],0,100))
    state.ball.position=np.asarray(pose['ball_position'],dtype=np.float32).copy()
    state.ball.linear_velocity=np.zeros(3,dtype=np.float32)
    state.ball.angular_velocity=np.zeros(3,dtype=np.float32)


def kickoff_reward(*, progress, closing, signed_ball_velocity, student_touches,
                   opponent_touches, first_touch, fake, ball_y, goal_outcome):
    """Short-horizon offense + first touch + possession proxy; bounded shaping."""
    score=.10*np.clip(progress/450.,-1.,1.)+.035*np.clip(closing/450.,-1.,1.)
    score+=.020*np.clip(signed_ball_velocity/2300.,-1.,1.)
    score+=.15*min(1,int(student_touches))-.08*min(1,int(opponent_touches))
    if first_touch=='student': score+=1.5
    if first_touch=='opponent':score-=.9
    # A fake is useful to exploit only if the student physically reaches the ball
    # and shifts it into opponent's territory. This is NOT a direct possession label.
    if fake and student_touches and ball_y>0:score+=.35
    score+=12.*goal_outcome-.002
    if not math.isfinite(score):raise FloatingPointError('Non-finite kickoff reward')
    return float(score)


class KickoffCurriculum(base.Native1v1):
    def __init__(self, actions, observer, opponents, poses, max_steps=180, device='cpu'):
        super().__init__(actions,observer,opponents['nexto'],max_steps,device)
        self.opponents=opponents
        self.poses=tuple(poses)
        self.episode_count=0
        self.student_side='blue'
        self.mode='nexto'
        self.replay_used=False
        self.first_touch=None
        self.first_touch_step=None
        self.fake_actual_no_contact=None
        self.student_touch_events=0
        self.opponent_touch_events=0
        self.fake_takeover=False
        self.latest_distance=0.

    def reset(self, seed):
        random.seed(int(seed))
        np.random.seed(int(seed)%(2**32))
        i=self.episode_count
        self.episode_count+=1
        self.student_side=('blue' if i%2==0 else 'orange')
        self.mode=MODES[(i//2)%len(MODES)]
        # Deterministically interleave replay starting poses, if available.
        pick=(self.poses[(int(seed)+i)//2%len(self.poses)] if self.poses and i%3!=0 else None)
        self.replay_used=pick is not None
        state=self.engine.create_base_state()
        self.teams.apply(state,{})
        self.kickoff.apply(state,{})
        apply_pose(state,pick)
        self.state=self.engine.set_state(state,{})
        self.t=0; self.total_reward=0.
        self.touches=0;self.opponent_touches=0
        self.student_touch_events=0;self.opponent_touch_events=0
        self.first_touch=None;self.first_touch_step=None;self.fake_takeover=False
        self.previous={}
        self.obs=base.read_obs(self.state,self.previous,self.observer,self.student_side+'-0')
        return self.obs

    def step(self, student_action):
        s=self.student_side+'-0'
        oside='orange' if self.student_side=='blue' else 'blue'
        o=oside+'-0'
        sign=1. if self.student_side=='blue' else -1.
        ball_before=self.state.ball
        pre_ball_y=float(ball_before.position[1])
        dist_before=float(np.linalg.norm(self.state.cars[s].physics.position-ball_before.position))
        other_obs=base.read_obs(self.state,self.previous,self.observer,o)
        with torch.no_grad():
            idx=int(base.logits_of(self.opponents['cycle9'] if self.mode=='cycle9' else self.opponents['nexto'],
                                   base.to_tensors(other_obs,self.device)).argmax(-1).item())
        student_control=np.asarray(self.actions[int(student_action)],dtype=np.float32).copy()
        other_control=np.asarray(self.actions[idx],dtype=np.float32).copy()
        dist_opp=float(np.linalg.norm(self.state.cars[o].physics.position-ball_before.position))
        opponent_control=fake_controls(self.mode,self.t,dist_opp,other_control,side=oside)
        self.state=self.engine.step({s:np.repeat(student_control[None],base.ACTION_REPEAT,axis=0),
                                     o:np.repeat(opponent_control[None],base.ACTION_REPEAT,axis=0)}, {})
        self.previous={s:student_control,o:opponent_control}
        self.t+=1
        car=self.state.cars[s];other=self.state.cars[o];ball=self.state.ball
        st=int(car.ball_touches);ot=int(other.ball_touches)
        self.student_touch_events+=st;self.opponent_touch_events+=ot
        new_first=None
        if self.first_touch is None and (st or ot):
            new_first='both' if st and ot else ('student' if st else 'opponent')
            self.first_touch=new_first
            self.first_touch_step=self.t
        progress=sign*(float(ball.position[1])-pre_ball_y)
        signed_y=sign*float(ball.position[1])
        signed_ball_velocity=sign*float(ball.linear_velocity[1])
        closing=dist_before-float(np.linalg.norm(car.physics.position-ball.position))
        goal=bool(self.state.goal_scored)
        outcome=int(sign*np.sign(ball.position[1])) if goal else 0
        fake=self.mode in FAKE_MODES
        reward=kickoff_reward(progress=progress,closing=closing,signed_ball_velocity=signed_ball_velocity,
                              student_touches=st,opponent_touches=ot,first_touch=new_first,fake=fake,
                              ball_y=signed_y,goal_outcome=outcome)
        self.total_reward+=reward
        if fake and st and ot==0 and self.opponent_touch_events==0 and signed_y>0:
            self.fake_takeover=True
        done=goal or self.t>=self.max_steps
        self.obs=base.read_obs(self.state,self.previous,self.observer,s)
        info={'outcome':outcome,'reward':self.total_reward,'steps':self.t,'student_side':self.student_side,
              'mode':self.mode,'replay_used':self.replay_used,'first_touch':self.first_touch,
              'first_touch_step':self.first_touch_step,'fake_attempted':fake,
              'fake_opponent_no_touch':fake and self.opponent_touch_events==0,
              'fake_takeover_proxy':self.fake_takeover,
              'student_touches':self.student_touch_events,'opponent_touches':self.opponent_touch_events,
              'final_ball_progress':signed_y,'goal_scored':goal,'timeout':done and not goal}
        return self.obs,reward,done,info


def evaluate(actor, baseline, opponents, actions, observer, poses, episodes=24, max_steps=180, seed=9876543):
    env=KickoffCurriculum(actions,observer,opponents,poses,max_steps=max_steps)
    out=[]
    try:
        for i in range(episodes):
            episode_seed=seed+1103*i
            for name, model in (('original_u60',baseline),('candidate',actor)):
                env.episode_count=i
                obs=env.reset(episode_seed)
                signature=tuple(round(float(v),2) for side in ('blue','orange')
                                for v in env.state.cars[side+'-0'].physics.position)
                while True:
                    with torch.no_grad():
                        action=int(base.logits_of(model,base.to_tensors(obs)).argmax(-1).item())
                    obs,_,done,info=env.step(action)
                    if done:break
                row={'policy':name,'episode':i,'seed':episode_seed,'signature':signature,**info}
                out.append(row)
    finally:env.close()
    for i in range(episodes):
        r=[x for x in out if x['episode']==i]
        if len(r)!=2 or r[0]['signature']!=r[1]['signature'] or r[0]['mode']!=r[1]['mode']:
            raise RuntimeError('Paired kickoff scenario mismatch')
    def summarize(name):
        rows=[r for r in out if r['policy']==name]
        n=len(rows)
        results={
            'episodes':n,'wins':sum(r['outcome']>0 for r in rows),
            'losses':sum(r['outcome']<0 for r in rows),
            'first_touch_rate':round(sum(r['first_touch']=='student' for r in rows)/n,4),
            'first_opponent_touch_rate':round(sum(r['first_touch']=='opponent' for r in rows)/n,4),
            'avg_ball_progress_uu':round(float(np.mean([r['final_ball_progress'] for r in rows])),2),
            'avg_reward':round(float(np.mean([r['reward'] for r in rows])),3),
            'fake_attempts':sum(r['fake_attempted'] for r in rows),
            'fake_no_opponent_touch':sum(r['fake_opponent_no_touch'] for r in rows),
            'fake_takeover_proxy':sum(r['fake_takeover_proxy'] for r in rows),
            'replay_start_episodes':sum(r['replay_used'] for r in rows)
        }
        results['by_mode']={mode:{'games':len(sub),'first_touches':sum(x['first_touch']=='student' for x in sub),
                                   'wins':sum(x['outcome']>0 for x in sub),
                                   'fake_takeover_proxy':sum(x['fake_takeover_proxy'] for x in sub)}
                            for mode in MODES if (sub:=[r for r in rows if r['mode']==mode])}
        return results
    return {'original_u60':summarize('original_u60'),'candidate':summarize('candidate'),
            'seed':seed,'episodes':episodes,'notes':'Greedy, paired starts; fake possession only a trajectory proxy'}


def checked_u60(path,root,source_sha,nexto_sha):
    dest=Path(path).resolve()
    if not dest.is_relative_to((root/'data'/'isolated').resolve()) or not dest.is_file():
        raise ValueError('u60 checkpoint must be an existing .pt under data/isolated')
    if base.sha256(dest)!=EXPECTED_U60_SHA:raise RuntimeError('The protected u60 checkpoint hash changed or wrong checkpoint selected')
    doc=torch.load(dest,map_location='cpu',weights_only=True)
    if not (isinstance(doc,dict) and doc.get('stage')=='slater_v027' and doc.get('global_updates')==60 and
            doc.get('source_sha')==source_sha and doc.get('meta',{}).get('nexto_sha')==nexto_sha):
        raise ValueError('Expected original verified v027 u60 checkpoint')
    return doc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True,help='u60 v027 checkpoint')
    p.add_argument('--scenarios',default='data/kickoffs_v031',help='kickoff extraction root (optional)')
    p.add_argument('--run',required=True)
    p.add_argument('--updates',type=int,default=40)
    p.add_argument('--rollout-steps',type=int,default=1024)
    p.add_argument('--checkpoint-every',type=int,default=10)
    p.add_argument('--max-episode-steps',type=int,default=180)
    p.add_argument('--eval-episodes',type=int,default=36)
    p.add_argument('--actor-lr',type=float,default=3e-6)
    p.add_argument('--teacher-weight',type=float,default=.25)
    p.add_argument('--seed',type=int,default=20261011)
    a=p.parse_args()
    safe_run(a.run)
    if not (1<=a.updates<=1000 and 128<=a.rollout_steps<=8192 and 1<=a.checkpoint_every<=1000
            and 60<=a.max_episode_steps<=360 and 12<=a.eval_episodes<=200 and a.eval_episodes%12==0
            and 0<a.actor_lr<=1e-5 and .1<=a.teacher_weight<=1):p.error('Invalid safety parameters')
    root=Path.cwd().resolve()
    isolated=(root/'data'/'isolated').resolve()
    if any(isolated.glob(f'{a.run}_u*')):raise FileExistsError('Run prefix already used, choose a new one')
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA,cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    import slater_cycle9_paired_eval_v026_fixed as paired
    if base.sha256(root/CYCLE9)!=CYCLE9_SHA or base.sha256(root/'vendor'/'nexto'/'nexto-model.pt')!=EXPECTED_NEXTO_SHA256:
        raise RuntimeError('Protected original model SHA mismatch')
    torch.set_num_threads(2)
    torch.manual_seed(a.seed);random.seed(a.seed);np.random.seed(a.seed)
    doc=checked_u60(a.checkpoint,root,CYCLE9_SHA,EXPECTED_NEXTO_SHA256)
    actor,cycle9=cycle9_pair(root)
    actor.load_state_dict(doc['actor'],strict=True)
    u60,_=cycle9_pair(root)
    u60.load_state_dict(doc['actor'],strict=True)
    if any(p.data_ptr()==q.data_ptr() for p,q in zip(actor.parameters(),u60.parameters())):
        raise RuntimeError('Student shares storage with frozen u60 teacher')
    for model in (cycle9,u60):
        model.eval()
        for param in model.parameters():param.requires_grad_(False)
    nexto=torch.jit.load(str(root/'vendor'/'nexto'/'nexto-model.pt'),map_location='cpu')
    nexto.eval()
    for param in nexto.parameters():param.requires_grad_(False)
    native=nexto_actions()
    actions=np.stack([np.asarray(native[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape!=(90,8) or not np.isfinite(actions).all():raise RuntimeError('Bad 90-action lookup')
    # An independent clone of u60 is the specialist's KL anchor.
    opponents={'nexto':nexto,'cycle9':cycle9}
    scenario_root=(root/a.scenarios).resolve()
    train_poses=load_poses(scenario_root,'train')
    val_poses=load_poses(scenario_root,'validation')
    print('KICKOFF_CURRICULUM_START from frozen u60; action vocabulary 90; NO REAL SPEEDFLIP ACTION',flush=True)
    print('SPLITS',json.dumps({'train':len(train_poses),'validation':len(val_poses),'heldout_replays_used':False}),flush=True)
    if not train_poses:print('WARNING: no replay-seeded train snapshots; using procedural mutator positions only',flush=True)
    critic=base.ValueNet()
    actor_opt=torch.optim.Adam(actor.parameters(),lr=a.actor_lr)
    critic_opt=torch.optim.Adam(critic.parameters(),lr=2e-4)
    observer=TeamObserver()
    before=evaluate(actor,u60,opponents,actions,observer,val_poses,a.eval_episodes,a.max_episode_steps,a.seed+8000000)
    print('BASELINE_KICKOFF_EVAL',json.dumps(before,sort_keys=True),flush=True)
    env=KickoffCurriculum(actions,observer,opponents,train_poses,a.max_episode_steps)
    started=time.perf_counter()
    reports=[]
    try:
        for update in range(1,a.updates+1):
            data,ends=base.collect(actor,critic,env,a.rollout_steps,a.seed+update*1933,'cpu')
            info=base.update(actor,u60,critic,actor_opt,critic_opt,data,2,128,a.teacher_weight,a.seed+update,'cpu')
            info.update({'update':update,'episodes':len(ends),'student_first':sum(x['first_touch']=='student' for x in ends),
                         'opponent_first':sum(x['first_touch']=='opponent' for x in ends),
                         'fake_episodes':sum(x['fake_attempted'] for x in ends),
                         'fake_takeover_proxy':sum(x['fake_takeover_proxy'] for x in ends),
                         'replay_episodes':sum(x['replay_used'] for x in ends),
                         'wins':sum(x['outcome']==1 for x in ends),'losses':sum(x['outcome']==-1 for x in ends)})
            print('UPDATE',json.dumps(info,sort_keys=True),flush=True)
            reports.append(info)
            if update % a.checkpoint_every==0 or update==a.updates:
                result=evaluate(actor,u60,opponents,actions,observer,val_poses,a.eval_episodes,a.max_episode_steps,a.seed+8000000)
                print('KICKOFF_EVAL',update,json.dumps(result,sort_keys=True),flush=True)
                if base.sha256(root/CYCLE9)!=CYCLE9_SHA or base.sha256(root/'vendor'/'nexto'/'nexto-model.pt')!=EXPECTED_NEXTO_SHA256:
                    raise RuntimeError('Original models changed')
                checkpoint=isolated/f'{a.run}_u{update:04d}.pt'
                report=isolated/f'{a.run}_u{update:04d}.json'
                base.check_output(checkpoint,root)
                base.check_output(report,root,'.json')
                metadata={'stage':'slater_kickoff_v031','source_sha':CYCLE9_SHA,'nexto_sha':EXPECTED_NEXTO_SHA256,
                          'u60_sha':base.sha256(Path(a.checkpoint).resolve()),'from_update':60,
                          'global_updates':update,'run':a.run,'args':vars(a),'evaluation':result,
                          'baseline':before,'recent_stats':reports[-a.checkpoint_every:],
                          'warnings':'Kickoff-only 90 actions, fake proxies not true fake classifications. Never auto-promote.'}
                base.save_create_only(checkpoint,{'stage':'slater_kickoff_v031','actor':actor.state_dict(),
                    'critic':critic.state_dict(),'actor_optimizer':actor_opt.state_dict(),
                    'critic_optimizer':critic_opt.state_dict(),'source_sha':CYCLE9_SHA,
                    'global_updates':update,'meta':metadata})
                report.parent.mkdir(parents=True,exist_ok=True)
                with report.open('x',encoding='utf8') as f:json.dump(metadata,f,indent=2)
                print('SAVED_ISOLATED',checkpoint,flush=True)
    finally:env.close()
    u60_hash_ok=base.sha256(Path(a.checkpoint).resolve())==EXPECTED_U60_SHA
    cycle_hash_ok=base.sha256(root/CYCLE9)==CYCLE9_SHA
    nexto_hash_ok=base.sha256(root/'vendor'/'nexto'/'nexto-model.pt')==EXPECTED_NEXTO_SHA256
    if not (u60_hash_ok and cycle_hash_ok and nexto_hash_ok):
        raise RuntimeError('One of the immutable source checkpoints changed')
    print('SUMMARY',json.dumps({'updates':a.updates,'transitions':a.updates*a.rollout_steps,
        'seconds':round(time.perf_counter()-started,2),'source_u60_untouched':u60_hash_ok,
        'original_cycle9_untouched':cycle_hash_ok,'original_nexto_untouched':nexto_hash_ok,
        'NO_PROMOTION':True}),flush=True)

if __name__=='__main__':main()
