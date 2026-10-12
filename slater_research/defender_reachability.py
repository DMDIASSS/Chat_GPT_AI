"""v0.1.9 read-only counterfactual reachability sweep for verified 1v1 defender scenarios.

Not PPO. Not a save certification. Start with a verified replay-control goal,
then try independent, physically dynamic defender control policies. A timeout
is recorded as 'no goal by deadline', not a save; a touch is recorded separately.
Do not use the holdout splits for candidate search/hyperparameter selection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Callable

import numpy as np

from slater_research.counterfactual_audit import select_candidates
from slater_research.replay_engine import Clip
from slater_research.verified_defender_env import VerifiedDefenderEnv

# All override actions are constrained to RocketSim's 8-control protocol:
# throttle, steer, pitch, yaw, roll, jump, boost, handbrake.
POLICIES = (
    'replay', 'neutral', 'brake', 'boost', 'turn_left', 'turn_right',
    'boost_left', 'boost_right', 'powerslide_left', 'powerslide_right',
    'jump_boost', 'pursuit_left', 'pursuit_right',
)


def pursuit_action(state, defender_id: int, *, turn_sign: int, lead_s: float = 0.30) -> np.ndarray:
    """A deliberately simple *reactive* pursuit baseline (no future replay leakage).

    Uses only current simulated ball/car physics. Both yaw sign conventions are
    explored because the basis/orientation convention may differ across clients.
    """
    if turn_sign not in (-1, 1):
        raise ValueError('turn_sign must be -1 or 1')
    car=state.cars[defender_id]
    cp=np.asarray(car.physics.position,dtype=np.float64).reshape(3)
    rotation=np.asarray(car.physics.rotation_mtx,dtype=np.float64).reshape(3,3)
    bp=np.asarray(state.ball.position,dtype=np.float64).reshape(3)
    bv=np.asarray(state.ball.linear_velocity,dtype=np.float64).reshape(3)
    if not all(np.isfinite(a).all() for a in (cp,rotation,bp,bv)):
        raise ValueError('Nonfinite simulated physics')
    # Projected intercept is bounded to avoid targeting far outside the arena.
    target=bp+np.clip(lead_s,0,0.5)*bv
    delta=target[:2]-cp[:2]
    forward=rotation[:2,0]
    fmag=float(np.linalg.norm(forward))
    if fmag<1e-6:
        raise ValueError('Invalid forward vector')
    forward=forward/fmag
    if np.linalg.norm(delta)<1e-5:
        yaw_err=0.0
    else:
        yaw_err=math.atan2(float(forward[0]*delta[1]-forward[1]*delta[0]),
                           float(np.dot(forward,delta)))
    steer=float(np.clip(turn_sign*yaw_err/0.65,-1.0,1.0))
    action=np.zeros(8,dtype=np.float32)
    action[0]=1.0
    action[1]=steer
    action[6]=1.0 if abs(yaw_err)<0.32 else 0.0
    return action


def policy_action(name: str, state, defender_id: int, *, step_index: int,
                  replay_action: np.ndarray) -> np.ndarray:
    if name not in POLICIES:
        raise ValueError(f'Unknown policy: {name}')
    if name=='replay':
        a=np.asarray(replay_action,dtype=np.float32).copy()
    elif name=='pursuit_left':
        a=pursuit_action(state,defender_id,turn_sign=-1)
    elif name=='pursuit_right':
        a=pursuit_action(state,defender_id,turn_sign=1)
    else:
        a=np.zeros(8,dtype=np.float32)
        if name=='brake':a[0]=-1.
        elif name in ('boost','boost_left','boost_right','jump_boost'):
            a[0]=1.;a[6]=1.
        elif name in ('turn_left','turn_right','powerslide_left','powerslide_right'):
            a[0]=1.
        if name in ('turn_left','boost_left','powerslide_left'):a[1]=-1.
        elif name in ('turn_right','boost_right','powerslide_right'):a[1]=1.
        if name.startswith('powerslide'):a[7]=1.
        # Edge-triggered jump; do not hold jump for the entire episode.
        if name=='jump_boost' and step_index==0:a[5]=1.
    if a.shape!=(8,) or not np.isfinite(a).all() or np.any(np.abs(a)>1.0001):
        raise ValueError(f'Invalid action for {name}')
    return a


def run_policy(clip: Clip, candidate: dict, policy: str, engine_factory: Callable) -> dict:
    if policy not in POLICIES: raise ValueError(policy)
    engine=engine_factory()
    try:
        env=VerifiedDefenderEnv(clip,candidate,engine,train_only=True)
        endpoint=None
        first_touch_frame=None
        while not env.done:
            replay=env.replay_actions()
            overrides={aid:policy_action(policy,env.state,aid,
                                         step_index=env.i-env.start,
                                         replay_action=replay[aid]) for aid in env.defenders}
            _,_,_,info=env.step(overrides)
            if any(env.last_touch.values()) and first_touch_frame is None:
                first_touch_frame=env.i
            if env.i==env.goal:
                endpoint=np.asarray(env.state.ball.position,dtype=float).tolist()
        result=env.result()
        # Signed status from v0.1.8; a timeout is deliberately NOT a save.
        return {
            'policy':policy,'status':result.status,
            'attacker_scored':result.attacker_scored,
            'defender_scored':result.defender_scored,
            'no_goal_by_deadline':result.status=='no_goal_by_deadline',
            'goal_step':result.goal_step,
            'goal_offset_s':result.goal_offset_s,
            'endpoint_ball_error_uu':result.endpoint_ball_error_uu,
            'peak_reference_error_uu':result.peak_reference_error_uu,
            'endpoint_ball_xyz':endpoint,
            'defender_touch_observed':result.defender_touch_observed,
            'first_defender_touch_step':first_touch_frame,
            'completed_steps':result.completed_steps,
        }
    finally:
        engine.close()


def baseline_accepted(run: dict, *, max_error_uu: float = 250.) -> bool:
    if not run['attacker_scored'] or run['goal_offset_s'] is None or run['goal_offset_s']<0:
        return False
    ep=run['endpoint_ball_error_uu'];peak=run['peak_reference_error_uu']
    return (ep is not None and peak is not None and math.isfinite(ep) and
            math.isfinite(peak) and max(ep,peak)<=max_error_uu)


def compare_intervention(base: dict, probe: dict) -> dict:
    """Observation only, never declare 'saved' for no goal by deadline."""
    endpoint_diversion=None
    if base['endpoint_ball_xyz'] is not None and probe['endpoint_ball_xyz'] is not None:
        endpoint_diversion=float(np.linalg.norm(np.asarray(probe['endpoint_ball_xyz'])-
                                                  np.asarray(base['endpoint_ball_xyz'])))
    return {
        **probe,
        'changed_goal_outcome_by_deadline':bool(not probe['attacker_scored']),
        'touch_and_no_goal_by_deadline':bool(probe['defender_touch_observed'] and
                                            probe['no_goal_by_deadline']),
        'endpoint_diversion_from_reference_uu':endpoint_diversion,
        'interpretation': ('confirmed_defender_goal' if probe['defender_scored'] else
                           'attacker_goal_still_scored' if probe['attacker_scored'] else
                           'no_attacker_goal_by_deadline_not_a_confirmed_save'),
    }


def audit_one(clip: Clip, candidate: dict, engine_factory, *, max_error_uu=250.,
              policies=POLICIES):
    if not policies or policies[0]!='replay' or len(set(policies))!=len(policies) or any(p not in POLICIES for p in policies):
        raise ValueError('First policy must be replay and all policies unique and recognized')
    result={'clip_file':candidate['clip_file'],'replay_sha256':candidate['replay_sha256'],
            'split':candidate['split'],'window_s':candidate['window_s'],'runs':[]}
    positive=run_policy(clip,candidate,'replay',engine_factory)
    result['runs'].append(positive)
    result['baseline_accepted']=baseline_accepted(positive,max_error_uu=max_error_uu)
    if not result['baseline_accepted']:
        result['status']='baseline_failed';return result
    for policy in policies[1:]:
        probe=run_policy(clip,candidate,policy,engine_factory)
        result['runs'].append(compare_intervention(positive,probe))
    result['status']='probes_complete'
    return result


def audit(clips: Path, catalog: dict, *, limit=12, max_error_uu=250.,
          engine_factory=None, progress=print):
    if engine_factory is None:
        from rlgym.rocket_league.sim import RocketSimEngine
        engine_factory=lambda:RocketSimEngine(rlbot_delay=False)
    if not clips.is_dir(): raise FileNotFoundError(clips)
    if not math.isfinite(max_error_uu) or max_error_uu<=0:raise ValueError('Invalid max error')
    selected=select_candidates(catalog,'train',limit)
    rows=[]
    for index,candidate in enumerate(selected,1):
        try:
            clip=Clip.load(clips/candidate['clip_file'])
            row=audit_one(clip,candidate,engine_factory,max_error_uu=max_error_uu)
        except Exception as exc:
            row={'clip_file':candidate['clip_file'],'status':'error',
                 'error':f'{type(exc).__name__}: {exc}'}
        rows.append(row)
        total=sum(x.get('changed_goal_outcome_by_deadline',False)
                  for x in row.get('runs',[])[1:])
        progress(f'[{index}/{len(selected)}] {candidate["clip_file"]}: {row["status"]} '
                 f'changed_deadline={total} error={row.get("error","-")}',flush=True)
    complete=[x for x in rows if x['status']=='probes_complete']
    probes=[run for row in complete for run in row['runs'][1:]]
    return {
        'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
        'purpose':'Read-only short-horizon, all-dynamic defender reachability exploration',
        'warning':('A change of goal outcome by deadline is NOT a certified save. '
                   'Only train split is searched. Validated defense and held-out policy comparisons '
                   'are necessary before PPO or any checkpoint promotion.'),
        'summary':{
            'selected':len(selected),
            'reproduced_baselines':len(complete),
            'baseline_failures':sum(r['status']=='baseline_failed' for r in rows),
            'exceptions':sum(r['status']=='error' for r in rows),
            'probe_trials':len(probes),
            'changed_deadline_trials':sum(p['changed_goal_outcome_by_deadline'] for p in probes),
            'changed_deadline_clips':sum(any(p['changed_goal_outcome_by_deadline'] for p in r['runs'][1:]) for r in complete),
            'defender_touch_trials':sum(p['defender_touch_observed'] for p in probes),
            'touch_and_no_goal_trials':sum(p['touch_and_no_goal_by_deadline'] for p in probes),
        },
        'policies':list(POLICIES),'cases':rows,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',required=True)
    p.add_argument('--catalog',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--limit',type=int,default=12)
    p.add_argument('--max-error',type=float,default=250.)
    args=p.parse_args(argv)
    if args.limit<1 or not math.isfinite(args.max_error) or args.max_error<=0:
        p.error('Invalid --limit or --max-error')
    dst=Path(args.out)
    if dst.exists() or dst.with_name(dst.name+'.partial').exists():
        p.error('Output or partial file already exists; refuse to overwrite')
    with Path(args.catalog).open('r',encoding='utf-8') as f:
        catalog=json.load(f)
    result=audit(Path(args.clips),catalog,limit=args.limit,max_error_uu=args.max_error)
    dst.parent.mkdir(parents=True,exist_ok=True)
    partial=dst.with_name(dst.name+'.partial')
    with partial.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    os.replace(partial,dst)
    print('SUMMARY '+str(result['summary']))
    print('READ-ONLY: no PPO or checkpoint changes. No deadline timeout is called a confirmed save.')
    return result

if __name__=='__main__':main()
