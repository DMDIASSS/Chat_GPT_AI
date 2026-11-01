"""Frozen attention-teacher labels on native student states; no learner overrides."""
import json,random
from pathlib import Path
import numpy as np
import torch
from nexto_teacher import nexto_actions
from slater_native_actor import NativeActor,packet,action_mask,checkpoint_identity
from slater_native_eval import load,Controller,check_pause
from slater_native_teacher_repair import bank_rows
from slater_v041_core import atomic_json,read_json,sha256


def project_controls(probabilities,car):
    """Map all teacher probability mass to feasible, physically similar controls.

    Dropping masked actions discards valid ground throttle/boost expressed through
    an aerial action. Ignore aerial axes only for a grounded non-jump action.
    """
    table=nexto_actions();mask=action_mask(car);available=np.flatnonzero(mask)
    probs=np.asarray(probabilities,dtype=np.float64)
    if probs.shape!=(90,) or not np.isfinite(probs).all() or np.any(probs<0) or probs.sum()<=0:raise ValueError('Invalid teacher probabilities')
    weights=np.tile([1.,1.,1.,1.,1.,8.,4.,2.],(90,1))
    if car['ground']:weights[table[:,5]==0,2:5]=0
    cost=np.sum((table[:,None]-table[available][None])**2*weights[:,None],axis=-1)
    # Preserve exact feasible action IDs when several controls are equivalent.
    mapping=available[cost.argmin(-1)];mapping[mask]=np.flatnonzero(mask)
    target=np.bincount(mapping,weights=probs/probs.sum(),minlength=90).astype(np.float32)
    assert not np.any(target[~mask])
    return target


class FrozenTeacher:
    def __init__(self,path):
        self.path=Path(path);self.digest=sha256(path);self.actor=load(path)
        if isinstance(self.actor,NativeActor):raise ValueError('Teacher must be the attention .pt checkpoint')
        self.actor.eval()
        for parameter in self.actor.parameters():parameter.requires_grad_(False)
        from afk_team_research import TeamObserver
        self.observer=TeamObserver()

    def target(self,state,previous,query,engine):
        from slater_versatile_data import native_observation
        from slater_cycle9_native_ppo_v025 import logits_of
        obs=native_observation(self.observer.observe(state,previous)[query])
        with torch.inference_mode():
            logits=logits_of(self.actor,tuple(torch.from_numpy(x[None]) for x in obs))
            probs=logits.softmax(-1).numpy()[0]
        p,keys=packet(state,previous,engine);car=next(c for c in p['cars'] if c['id']==keys[query])
        return project_controls(probs,car),int(probs.argmax()),float(probs[8])


def collect(bank,teacher,student,*,stage='touch_warmup',difficulty=0,episodes=24,seconds=6,seed_base=15100000000,stop=None):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from slater_focus_evaluation import setup,Tracker
    from slater_event_windows import native_row
    from afk_team_research import TeamObserver
    if not 12<=episodes<=128 or not 2<=seconds<=12:raise ValueError('Invalid teacher collection budget')
    teacher=Path(teacher);student=Path(student);bank=Path(bank)
    identity=dict(teacher_sha=sha256(teacher),student=checkpoint_identity(student),stage=stage,difficulty=difficulty,episodes=episodes,seconds=seconds,seed_base=seed_base,collector_sha=sha256(__file__))
    if bank.exists():
        meta=read_json(bank.with_suffix('.json'))
        if meta.get('collection')!=identity or meta['bank_sha']!=sha256(bank):raise ValueError('Teacher collection changed; preserve this bank and use a new run')
        return meta
    frozen=FrozenTeacher(teacher);native=NativeActor(student);observer=TeamObserver();torch.set_num_threads(1)
    engine=RocketSimEngine(rlbot_delay=False);rows=[];records=[];groups={0:[],1:[],2:[]}
    try:
        for j in range(episodes):
            check_pause(stop);seed=seed_base+j;random.seed(seed);team=j%2;ours=('blue-' if team==0 else 'orange-')+'0';enemy=('orange-' if team==0 else 'blue-')+'0'
            split=2 if j%12<2 else 1 if j%12<4 else 0;groups[split].append(seed)
            state=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{});KickoffMutator().apply(state,{})
            # Half the behavior rollouts follow the teacher, half the raw student.
            # Include ordinary play for rehearsal; specialized starts use the current stage.
            general=j//2%3==2;mode='teacher' if j//2%2==0 else 'student'
            if not general and not stage.startswith('replay_'):setup(state,stage,ours,enemy,seed,difficulty)
            state=engine.set_state(state,{});ids=sorted(state.cars,key=lambda aid:state.cars[aid].team_num)
            learner=Controller(frozen.actor if mode=='teacher' else native,scripted=False);rival=Controller(frozen.actor,scripted=True)
            tracker=Tracker('touch_warmup',state,ours,enemy);previous={};active=0;distance=0.;touched=False
            for tick in range(round(seconds*120)):
                if tick%120==0:check_pause(stop)
                kickoff=(general or stage=='kickoff') and not touched and tick<168 and np.linalg.norm(state.ball.position[:2])<1
                if tick%16==0:
                    target,raw,raw_idle=frozen.target(state,previous,ours,engine)
                    row=native_row(state,ids,previous,ours,target,1,split)
                    # Match the native packet's pad order rather than wheel enumeration.
                    p,_=packet(state,previous,engine);row[18:52]=p['timers'];rows.append(row)
                a=learner.controls(state,ours,previous,engine,tick,kickoff,observer);b=rival.controls(state,enemy,previous,engine,tick,kickoff,observer)
                before=state;state=engine.step({ours:a[None],enemy:b[None]},{});tracker.tick(before,state,a)
                distance+=float(np.linalg.norm(state.cars[ours].physics.position-before.cars[ours].physics.position));active+=bool(np.any(a));previous={ours:a.copy(),enemy:b.copy()};touched|=any(c.ball_touches for c in state.cars.values())
                if state.goal_scored:break
            records.append(dict(seed=seed,split=split,side='blue' if team==0 else 'orange',mode=mode,active_fraction=active/(tick+1),distance=distance,touched=tracker.touch,scored=bool(state.goal_scored and tracker.sign*state.ball.position[1]>0)))
            print('FROZEN_TEACHER_COLLECT',j+1,'/',episodes,mode,'active',round(active/(tick+1),3),'touch',tracker.touch,'rows',len(rows),flush=True)
    finally:engine.close()
    if sha256(teacher)!=frozen.digest or checkpoint_identity(student)!=identity['student']:raise RuntimeError('Protected teacher/student changed during collection')
    teacher_records=[r for r in records if r['mode']=='teacher']
    for side in ('blue','orange'):
        if not any(r['side']==side and r['active_fraction']>.1 and r['distance']>100 for r in teacher_records):
            raise RuntimeError(f'Teacher playback is inactive on {side}; no teacher bank will be used. Check teacher checkpoint/adapter.')
    meta=bank_rows(rows,bank,teacher,groups)
    meta.update(collection=identity,rollouts=records,teacher_movement_verified=True,
                teacher_touch_episodes=sum(r['touched'] for r in teacher_records),student_touch_episodes=sum(r['touched'] for r in records if r['mode']=='student'),
                note='Frozen current-state teacher; mixed teacher/student behavior and replayed-label action projection. Episode-grouped splits. No teacher controls enter native learner PPO.')
    atomic_json(bank.with_suffix('.json'),meta);return meta
