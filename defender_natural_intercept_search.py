r"""Read-only diagnostic: search for defender contacts from ORIGINAL, unmodified car starts.

Important: some policies use FUTURE REPLAY BALL POSITIONS as an optimistic
interception oracle. Those inputs are privileged, unsuitable for deployment or
RL training. A contact is a real RocketSim collision, but a missed scoring
DEADLINE is NOT a confirmed save. No checkpoint/NPZ/source mutation.

Windows CMD example:
  .venv\Scripts\python.exe defender_natural_intercept_search.py --clips data\replay_scenarios_carfix_v020_12 --catalog data\replay_scenarios_carfix_v020_12\catalog_repaired_v020_11.json --out data\replay_scenarios_carfix_v020_12\natural_intercept_search.json --limit 4 --probes 64
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TICKS_PER_DECISION = 8
SECONDS_PER_DECISION = TICKS_PER_DECISION / 120.0


@dataclass(frozen=True)
class Probe:
    target: str  # reactive: current physics+velocity; oracle: future replay position
    lead: float
    turn_sign: int
    pitch_sign: int
    jump_at: int  # -1 means no jump
    boost: str  # always | aligned
    handbrake: bool

    def label(self) -> str:
        return (f'{self.target}:lead={self.lead:g}:turn={self.turn_sign:+d}:'
                f'pitch={self.pitch_sign:+d}:jump={self.jump_at}:'
                f'boost={self.boost}:slide={int(self.handbrake)}')


def get_probes(limit=64):
    """Deterministic, varied policy subset with paired yaw directions."""
    if not isinstance(limit, int) or limit < 1 or limit > 512:
        raise ValueError('probes must be between 1 and 512')
    base=[]
    for target, lead, sign, pitch, jump, boost, slide in itertools.product(
            ('reactive','oracle'), (0., .2, .4, .6), (-1,1), (-1,1),
            (-1,0,2), ('always','aligned'), (False,True)):
        base.append(Probe(target, lead, sign, pitch, jump, boost, slide))
    # Deterministic spread without tailoring hyperparameters on holdouts.
    rng=np.random.default_rng(20261011)
    order=rng.permutation(len(base))
    return [base[int(i)] for i in order[:limit]]


def _xyz(value):
    a=np.asarray(value, dtype=float).reshape(3)
    if not np.isfinite(a).all():
        raise ValueError('Nonfinite physics data')
    return a


def policy_action(probe: Probe, state, defender_id, *, step_index, clip, absolute_index, goal_index):
    car=state.cars[defender_id]
    cp=_xyz(car.physics.position)
    bp=_xyz(state.ball.position)
    bv=_xyz(state.ball.linear_velocity)
    rotation=np.asarray(car.physics.rotation_mtx,dtype=float).reshape(3,3)
    if not np.isfinite(rotation).all():
        raise ValueError('Nonfinite rotation')
    if probe.target=='oracle':
        target_step=min(goal_index, absolute_index+int(round(probe.lead/SECONDS_PER_DECISION)))
        target=_xyz(clip.snapshots[target_step].ball.position)
    elif probe.target=='reactive':
        target=bp + probe.lead * bv
    else:
        raise ValueError('Invalid target mode')
    target=target.copy()  # Never mutate the replay snapshot or engine-owned ball state.
    target[:2]=np.clip(target[:2],[-3950.,-5050.],[3950.,5050.])
    d=target-cp
    forward=rotation[:2,0]
    denom=float(np.linalg.norm(forward))
    if denom<.01:
        # Airborne vertical orientation: use car's right axis instead.
        forward=np.asarray(rotation[:2,1],dtype=float)
        denom=float(np.linalg.norm(forward))
    if denom<.01:
        yaw_error=0.
    else:
        forward=forward/denom
        yaw_error=math.atan2(float(forward[0]*d[1]-forward[1]*d[0]),
                             float(np.dot(forward, d[:2])))
    vertical_error=math.atan2(float(d[2]),max(1.,float(np.linalg.norm(d[:2]))))
    action=np.zeros(8,dtype=np.float32)
    action[0]=1.
    steer=float(np.clip(probe.turn_sign * yaw_error/.55,-1.,1.))
    action[1]=steer
    action[3]=steer  # aerial yaw, same strategy sign sweep
    action[2]=float(np.clip(probe.pitch_sign*vertical_error/.5,-1.,1.))
    action[5]=float(step_index==probe.jump_at)
    action[6]=float(probe.boost=='always' or abs(yaw_error)<.6)
    action[7]=float(probe.handbrake and abs(yaw_error)>.6)
    if not np.isfinite(action).all() or np.max(abs(action))>1.:
        raise ValueError('Bad action')
    return action


def qualified_candidates(catalog, *, clips_dir: Path, limit: int):
    if not isinstance(catalog,dict) or not isinstance(catalog.get('candidates'),list):
        raise ValueError('Invalid catalog')
    rows=[]
    for c in catalog['candidates']:
        if c.get('split')!='train':
            continue
        if len(c.get('replay_sha256',''))!=64:
            raise ValueError('Invalid candidate SHA')
        name=c.get('clip_file')
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.npz'):
            raise ValueError('Unsafe clip filename')
        if not (clips_dir/name).is_file():
            continue
        rows.append(c)
    # Favor longer decision windows then nearby defenders. Don't search holdouts.
    rows.sort(key=lambda c:(-float(c['window_s']),float(c['start_min_defender_distance_uu']),c['clip_file']))
    return rows[:limit]


def rollout(clip,candidate,probe,engine_factory):
    from slater_research.verified_defender_env import VerifiedDefenderEnv
    engine=engine_factory()
    try:
        env=VerifiedDefenderEnv(clip,candidate,engine,train_only=True)
        defender=env.defenders[0]
        if env.state.cars[defender].is_demoed:
            raise ValueError('Demoed defender in tested window')
        initial=_xyz(env.state.cars[defender].physics.position)
        closest=float(np.linalg.norm(_xyz(env.state.ball.position)-initial))
        closest_at=env.start
        peak_car_move=0.
        touch_step=None
        while not env.done:
            control=policy_action(probe,env.state,defender,
                                  step_index=env.i-env.start,clip=clip,
                                  absolute_index=env.i,goal_index=env.goal)
            state,_,_,_=env.step({defender:control})
            dist=float(np.linalg.norm(_xyz(state.cars[defender].physics.position)-_xyz(state.ball.position)))
            moved=float(np.linalg.norm(_xyz(state.cars[defender].physics.position)-initial))
            if dist<closest:
                closest,closest_at=dist,env.i
            peak_car_move=max(peak_car_move,moved)
            if touch_step is None and env.last_touch[defender]:
                touch_step=env.i
        result=env.result()
        return {'policy':probe.label(),'oracle_future_replay_used':probe.target=='oracle',
                'status':result.status,'defender_touched':result.defender_touch_observed,
                'first_touch_step':touch_step,
                'min_car_ball_distance_uu':round(closest,3),
                'closest_step':closest_at,'max_car_displacement_uu':round(peak_car_move,3),
                'goal_step':result.goal_step,'endpoint_ball_error_uu':result.endpoint_ball_error_uu}
    finally:
        engine.close()


def check_baseline(clip,candidate,engine_factory,max_error=250.):
    from slater_research.verified_defender_env import VerifiedDefenderEnv
    engine=engine_factory()
    try:
        env=VerifiedDefenderEnv(clip,candidate,engine,train_only=True)
        if env.state.cars[env.defenders[0]].is_demoed:
            return {'accepted':False,'reason':'defender_demolished'}
        result=env.run_reference()
        accepted=(result.attacker_scored and result.goal_step is not None
                  and result.goal_step>=env.goal and
                  result.endpoint_ball_error_uu is not None and
                  result.peak_reference_error_uu is not None and
                  max(result.endpoint_ball_error_uu,result.peak_reference_error_uu)<=max_error)
        return {'accepted':bool(accepted),'reason':'pass' if accepted else 'goal_or_fidelity_failed',
                'goal_step':result.goal_step,'endpoint_error_uu':result.endpoint_ball_error_uu,
                'peak_error_uu':result.peak_reference_error_uu}
    finally:
        engine.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',required=True)
    p.add_argument('--catalog',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--limit',type=int,default=4)
    p.add_argument('--probes',type=int,default=64)
    args=p.parse_args(argv)
    if not 1<=args.limit<=44 or not 1<=args.probes<=512:
        p.error('limit must be 1-44; probes must be 1-512')
    clipdir=Path(args.clips)
    if not clipdir.is_dir():
        p.error(f'Clip directory missing: {clipdir}')
    dst=Path(args.out)
    if dst.exists() or dst.with_name(dst.name+'.partial').exists():
        p.error('Output or partial file already exists; cannot overwrite')
    with Path(args.catalog).open(encoding='utf-8') as f:
        catalog=json.load(f)
    candidates=qualified_candidates(catalog,clips_dir=clipdir,limit=args.limit)
    probes=get_probes(args.probes)
    from slater_research.replay_engine import Clip
    from rlgym.rocket_league.sim import RocketSimEngine
    engine_factory=lambda:RocketSimEngine(rlbot_delay=False)
    cases=[]
    for j,candidate in enumerate(candidates,1):
        row={'clip_file':candidate['clip_file'],'window_s':candidate['window_s'],
             'start_defender_ball_uu':candidate['start_min_defender_distance_uu'],
             'start_step':candidate['start_step'],'split':'train','baseline':None,
             'best':None,'probes_completed':0,'touches':0,'errors':0}
        try:
            clip=Clip.load(clipdir/candidate['clip_file'])
            if clip.replay_sha!=candidate['replay_sha256']:
                raise ValueError('Replay SHA mismatch')
            row['baseline']=check_baseline(clip,candidate,engine_factory)
            if row['baseline']['accepted']:
                best_dist=float('inf')
                best_touch=None
                for probe in probes:
                    try:
                        result=rollout(clip,candidate,probe,engine_factory)
                        row['probes_completed']+=1
                        row['touches']+=int(result['defender_touched'])
                        if result['min_car_ball_distance_uu']<best_dist:
                            best_dist=result['min_car_ball_distance_uu']
                            row['best_closest_approach']=result
                        if result['defender_touched']:
                            if best_touch is None or result['min_car_ball_distance_uu']<best_touch['min_car_ball_distance_uu']:
                                best_touch=result
                            row.setdefault('touch_examples',[]).append(result)
                    except Exception as e:
                        row['errors']+=1
                        if row['errors']<=3:
                            row.setdefault('sample_errors',[]).append(f'{type(e).__name__}: {e}')
                row['best']=best_touch if best_touch is not None else row.get('best_closest_approach')
                row['status']='probes_complete' if row['errors']==0 else 'probes_with_errors'
            else:
                row['status']='baseline_failed'
        except Exception as e:
            row['status']='error'
            row['error']=f'{type(e).__name__}: {e}'
        cases.append(row)
        best=row['best']
        print(f'[{j}/{len(candidates)}] {row["clip_file"]}: {row["status"]} '
              f'touches={row["touches"]}/{row["probes_completed"]} '
              f'closest={best["min_car_ball_distance_uu"] if best else "-"}uu',flush=True)
    good=[x for x in cases if x['status'] in ('probes_complete','probes_with_errors')]
    summary={'selected':len(candidates),'valid_baselines':len(good),
             'baseline_failures':sum(x['status']=='baseline_failed' for x in cases),
             'errors':sum(x['errors'] for x in cases)+sum(x['status']=='error' for x in cases),
             'probe_trials':sum(x['probes_completed'] for x in good),
             'defender_touch_trials':sum(x['touches'] for x in good),
             'clips_with_touch':sum(x['touches']>0 for x in good)}
    report={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
            'purpose':'Natural-start defender reachability diagnostic with reactive and optimistic replay-oracle controls',
            'warning':('Original defender car position/velocity/orientation is never changed. '
                       'ORACLE policies use future recorded replay ball states; they are unfair upper bounds '
                       'and must not become agent observations or training examples. '
                       'No goal by deadline is NOT a confirmed save. Train split only.'),
            'summary':summary,'cases':cases}
    dst.parent.mkdir(parents=True,exist_ok=True)
    temp=dst.with_name(dst.name+'.partial')
    with temp.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
    os.replace(temp,dst)
    print('SUMMARY',summary)
    print('READ ONLY — no checkpoint, PPO, source NPZ or champion modifications.')

if __name__=='__main__':
    main()
