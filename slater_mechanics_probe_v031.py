"""Slater v0.3.1 physical controls probe — NOT learned speedflip/halfflip.

Compares candidate tick-accurate control SEQUENCES with plain boosting from
identical RocketSim kickoff states. The source Nexto action table cannot express
jump+yaw simultaneous diagonal flip, even though RocketSim accepts per-tick
continuous controls. Results are diagnostic, NOT validated optimized mechanics.
"""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
import numpy as np
import slater_cycle9_native_ppo_v025 as base

FPS=120
TICKS=8


def input_action(throttle=1.,steer=0.,pitch=0.,yaw=0.,roll=0.,jump=0.,boost=1.,handbrake=0.):
    return np.array([throttle,steer,pitch,yaw,roll,jump,boost,handbrake],dtype=np.float32)


def macro_timeline(name,ticks=240):
    """Exploratory rough controller templates. Timing requires RocketSim tuning."""
    if name not in ('boost','speedflip_left_probe','speedflip_right_probe','halfflip_probe'):
        raise ValueError(name)
    a=np.stack([input_action() for _ in range(ticks)])
    if name.startswith('speedflip'):
        direction=-1. if 'left' in name else 1.
        # First jump, release, diagonal dodge (pitch+yaw), pitch-back cancel.
        a[22:29,5]=1.
        a[29:33,5]=0.
        a[33:35,2]=-1.
        a[33:35,3]=direction*.72
        a[33:35,5]=1.
        a[35:65,2]=1.
        a[35:65,4]=-direction*.68
        a[33:63,6]=1.
    elif name=='halfflip_probe':
        a[:20]=input_action(throttle=-1.,boost=0.)
        a[20:27]=input_action(throttle=-1.,pitch=1.,jump=1.,boost=0.)
        a[27:31]=input_action(throttle=-1.,boost=0.)
        a[31:33]=input_action(throttle=-1.,pitch=1.,jump=1.,boost=0.)
        a[33:64]=input_action(throttle=-1.,pitch=-1.,roll=1.,boost=0.)
        a[64:]=input_action(throttle=1.,boost=0.)
    return a


def audit_lookup(actions):
    a=np.asarray(actions)
    if a.ndim!=2 or a.shape[1]!=8:raise ValueError('Expected N x 8 controls')
    diagonal_jump=np.flatnonzero((a[:,5]>.5)&(np.abs(a[:,2])>.5)&(np.abs(a[:,3])>.5))
    return {'actions':len(a),'jump_with_diagonal_pitch_yaw':int(len(diagonal_jump)),
            'diagonal_jump_action_ids':diagonal_jump.tolist(),
            'physical_speedflip_expressible_as_single_action':bool(len(diagonal_jump)),
            'comment':'Missing simultaneous jump/pitch/yaw input means native table cannot directly request diagonal dodge'}


def one_probe(name,seed,ticks=240):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    random.seed(seed)
    np.random.seed(seed%(2**32))
    env=RocketSimEngine(rlbot_delay=False)
    try:
        state=env.create_base_state()
        FixedTeamSizeMutator(blue_size=1,orange_size=0).apply(state,{})
        KickoffMutator().apply(state,{})
        state=env.set_state(state,{})
        car=state.cars['blue-0'].physics
        p0=np.asarray(car.position,dtype=float).copy()
        f0=np.asarray(car.forward[:2],dtype=float).copy()
        ball0=np.asarray(state.ball.position,dtype=float).copy()
        frames=macro_timeline(name,ticks)
        samples=[]
        touches=0
        min_ball_sep=float(np.linalg.norm(p0-ball0))
        first_touch_tick=None
        for i in range(0,len(frames),TICKS):
            state=env.step({'blue-0':frames[i:i+TICKS]}, {})
            phy=state.cars['blue-0'].physics
            cpos=np.asarray(phy.position,dtype=float)
            dist=float(np.linalg.norm(cpos-np.asarray(state.ball.position,dtype=float)))
            min_ball_sep=min(min_ball_sep,dist)
            n=int(state.cars['blue-0'].ball_touches)
            touches+=n
            if n and first_touch_tick is None:first_touch_tick=i+TICKS
            if (i+TICKS)%(FPS//5)==0 or i+TICKS==ticks:
                samples.append({'t':round((i+TICKS)/FPS,3),
                    'position':[round(float(x),1) for x in cpos],
                    'speed':round(float(np.linalg.norm(phy.linear_velocity)),1),
                    'height':round(float(cpos[2]),1),
                    'ball_distance':round(dist,1),
                    'on_ground':bool(state.cars['blue-0'].on_ground)})
        c=state.cars['blue-0']
        f=np.asarray(c.physics.forward[:2],dtype=float)
        reverse_cos=float(np.dot(f,-f0)/(np.linalg.norm(f)*np.linalg.norm(f0)+1e-8))
        return {'name':name,'seed':seed,'touch_count':touches,
                'first_touch_s':None if first_touch_tick is None else round(first_touch_tick/FPS,3),
                'min_ball_distance':round(min_ball_sep,1),'horizontal_forward_progress_uu':round(float(np.dot(np.asarray(c.physics.position[:2],dtype=float)-p0[:2],f0)),1),
                'final_grounded':bool(c.on_ground),'final_height':round(float(c.physics.position[2]),1),
                'reverse_alignment_cosine':round(reverse_cos,3),'samples':samples}
    finally:env.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,default=200177)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    root=Path.cwd().resolve()
    dst=base.check_output(args.out,root,'.json')
    from nexto_teacher import nexto_actions
    native=nexto_actions()
    actions=np.stack([np.asarray(native[i],dtype=np.float32).reshape(8) for i in range(90)])
    audit=audit_lookup(actions)
    print('ACTION_SPACE_AUDIT',json.dumps(audit,sort_keys=True),flush=True)
    cases=['boost','speedflip_left_probe','speedflip_right_probe','halfflip_probe']
    results=[one_probe(name,args.seed) for name in cases]
    for result in results:
        print('MECHANICS_PROBE',json.dumps({k:v for k,v in result.items() if k!='samples'},sort_keys=True),flush=True)
    doc={'audit':audit,'probes':results,'warning':'Unoptimized experimental timed controls, NOT verified speedflip or half-flip. Use visual inspection.'}
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('x',encoding='utf8') as f:json.dump(doc,f,indent=2)
    print('SAVED_MECHANICS_AUDIT',dst,flush=True)
if __name__=='__main__':main()
