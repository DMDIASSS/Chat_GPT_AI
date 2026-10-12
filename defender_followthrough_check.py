"""Read-only post-contact diagnostic for ONE real-start reactive RocketSim intervention.

Requires existing Slater v0.2.0 and defender_natural_intercept_search.py.
Replays the original verified baseline and a particular REACTIVE probe that
previously touched the ball and had no goal by the short deadline. Then, without
resetting/teleporting cars, simulates an exploratory additional 3 seconds with
TWO attacker-control assumptions.

Beyond the recorded goal, attacker controls are unknown. This extended run is
NOT replay fidelity evidence, a confirmed save, a training example, or PPO.
Never modifies source clips, catalogs, Cycle 9, teacher, or checkpoints.

Windows CMD example:
 .venv\\Scripts\\python.exe defender_followthrough_check.py --clips data\\replay_scenarios_carfix_v020_12 --catalog data\\replay_scenarios_carfix_v020_12\\catalog_repaired_v020_11.json --out data\\replay_scenarios_carfix_v020_12\\followthrough_reactive_v020.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from defender_natural_intercept_search import Probe, policy_action

CLIP_FILE = '485530dc20c9d5_goal001.npz'
# Chosen from the TRAIN-only search; never tuned on holdout data.
PROBE = Probe('reactive', 0.2, +1, -1, 2, 'aligned', True)
PHYSICS_TICKS = 8
SECONDS_PER_STEP = PHYSICS_TICKS / 120.0
GOAL_THRESHOLD = 5215.5


def finite_xyz(value):
    array = np.asarray(value, dtype=np.float64).reshape(3)
    if not np.all(np.isfinite(array)):
        raise ValueError('Non-finite position or velocity')
    return [round(float(v), 3) for v in array]


def scoring_team(state, attacker_orange: bool):
    """Return only the first observed score classification, not a save label."""
    if not bool(state.goal_scored):
        return None
    # Blue scores at +Y, Orange at -Y.
    attack_direction = -1.0 if attacker_orange else 1.0
    return 'attacker_goal' if float(state.ball.position[1]) * attack_direction > 0 else 'defender_goal'


def moment(state, *, frame: int, reference_goal: int, attacker_orange: bool, touched: bool):
    bp = finite_xyz(state.ball.position)
    bv = finite_xyz(state.ball.linear_velocity)
    sign = -1.0 if attacker_orange else 1.0
    return {
        'frame': int(frame),
        'seconds_from_reference_goal': round((frame-reference_goal)*SECONDS_PER_STEP, 4),
        'ball_xyz': bp,
        'ball_velocity': bv,
        'ball_toward_attacker_goal_velocity_y': round(sign*bv[1], 3),
        'ball_distance_to_attacker_goal_plane_y': round(GOAL_THRESHOLD-sign*bp[1], 3),
        'defender_touch_this_step': bool(touched),
        'score_signal': scoring_team(state, attacker_orange),
    }


def candidate_from_catalog(catalog, clip_file=CLIP_FILE):
    rows = [x for x in catalog.get('candidates', []) if x.get('clip_file') == clip_file]
    if len(rows) != 1:
        raise ValueError(f'Expected exactly one candidate for {clip_file}; got {len(rows)}')
    row = rows[0]
    if row.get('split') != 'train':
        raise ValueError('Refusing non-train candidate')
    if Path(row['clip_file']).name != row['clip_file']:
        raise ValueError('Unsafe clip filename')
    return row


def make_commands(clip, env, defender_id, decision, *, attacker_mode: str):
    if attacker_mode not in ('repeat_last', 'neutral'):
        raise ValueError('Unknown attacker mode')
    controls = {}
    for aid in clip.ids:
        if aid == defender_id:
            cmd = decision
        elif attacker_mode == 'repeat_last':
            cmd = clip.controls[env.goal, env.index[aid]]
        else:
            cmd = np.zeros(8, dtype=np.float32)
        a = np.asarray(cmd, dtype=np.float32)
        if a.shape != (8,) or not np.all(np.isfinite(a)) or np.max(np.abs(a)) > 1.0001:
            raise ValueError('Bad controls')
        controls[aid] = np.tile(a, (PHYSICS_TICKS, 1))
    return controls


def run_probe_and_continue(clip, candidate, *, attacker_mode: str, extra_seconds: float):
    from rlgym.rocket_league.sim import RocketSimEngine
    from slater_research.verified_defender_env import VerifiedDefenderEnv
    engine = RocketSimEngine(rlbot_delay=False)
    try:
        env = VerifiedDefenderEnv(clip, candidate, engine, train_only=True)
        defender = env.defenders[0]
        if env.state.cars[defender].is_demoed:
            raise ValueError('Defender is demolished at scenario start')
        touch_frames=[]
        original_trace=[]
        while not env.done:
            before = finite_xyz(env.state.ball.linear_velocity)
            decision = policy_action(PROBE, env.state, defender,
                                     step_index=env.i-env.start,
                                     clip=clip, absolute_index=env.i,goal_index=env.goal)
            state, _, _, _ = env.step({defender:decision})
            touched = bool(env.last_touch[defender])
            if touched:
                touch_frames.append(env.i)
                original_trace.append({'frame':env.i,
                                       'ball_velocity_before_step':before,
                                       'ball_velocity_after_step':finite_xyz(state.ball.linear_velocity)})
        end_of_window=env.result()
        deadline_moment = moment(env.state, frame=env.i, reference_goal=env.goal,
                                 attacker_orange=env.attacker_orange,
                                 touched=bool(env.last_touch[defender]))
        if end_of_window.status != 'no_goal_by_deadline':
            return {'attacker_mode':attacker_mode,
                    'original_window_status':end_of_window.status,
                    'first_touch_step':touch_frames[0] if touch_frames else None,
                    'touch_frames':touch_frames,
                    'contact_velocities':original_trace,
                    'deadline_moment':deadline_moment,
                    'extension_status':'not_run_original_window_scored',
                    'extended_steps':0}
        trace=[deadline_moment]
        # We have reached env.done. Continued rollout runs straight through the
        # injected engine, without changing positions or physics flags.
        steps=int(math.ceil(extra_seconds/SECONDS_PER_STEP-1.e-10))
        state=env.state
        start_frame=env.i
        first_score=None
        additional_contacts=[]
        for j in range(steps):
            decision=policy_action(PROBE, state, defender,
                                   step_index=(start_frame+j)-env.start,
                                   clip=clip,absolute_index=start_frame+j,
                                   goal_index=env.goal)
            commands=make_commands(clip, env, defender, decision, attacker_mode=attacker_mode)
            state=engine.step(commands, {})
            frame=start_frame+j+1
            contact=bool(state.cars[defender].ball_touches)
            if contact:
                additional_contacts.append(frame)
            sample=moment(state,frame=frame,reference_goal=env.goal,
                          attacker_orange=env.attacker_orange,touched=contact)
            trace.append(sample)
            if sample['score_signal'] is not None:
                first_score={'status':sample['score_signal'],
                             'frame':frame,
                             'seconds_after_original_deadline':round((j+1)*SECONDS_PER_STEP,4)}
                break
        yvel=[t['ball_toward_attacker_goal_velocity_y'] for t in trace]
        dist=[t['ball_distance_to_attacker_goal_plane_y'] for t in trace]
        # Preserve trajectory samples at roughly 0.5 sec; retain all data only
        # for the first 3 seconds (max ~45 entries).
        return {'attacker_mode':attacker_mode,
                'original_window_status':end_of_window.status,
                'first_touch_step':touch_frames[0] if touch_frames else None,
                'touch_frames':touch_frames,
                'contact_velocities':original_trace,
                'deadline_moment':deadline_moment,
                'extension_status':first_score['status'] if first_score else 'no_goal_within_exploratory_extension',
                'first_extended_score':first_score,
                'extended_steps':len(trace)-1,
                'additional_contact_steps':additional_contacts,
                'closest_ball_distance_to_attack_goal_plane_uu':round(min(dist),3),
                'max_ball_velocity_toward_attack_goal_uu_s':round(max(yvel),3),
                'max_ball_velocity_away_from_attack_goal_uu_s':round(min(yvel),3),
                'trace':trace}
    finally:
        engine.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',required=True)
    p.add_argument('--catalog',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--extra-seconds',type=float,default=3.0)
    args=p.parse_args(argv)
    if not math.isfinite(args.extra_seconds) or not 0.25<=args.extra_seconds<=5:
        p.error('--extra-seconds must be from 0.25 to 5')
    clip_dir=Path(args.clips)
    file_path=clip_dir/CLIP_FILE
    if not file_path.is_file():
        p.error(f'Missing clip: {file_path}')
    out_path=Path(args.out)
    if out_path.exists() or out_path.with_name(out_path.name+'.partial').exists():
        p.error('Output/partial already exists; no overwrite allowed')
    with open(args.catalog,encoding='utf-8') as f:
        catalog=json.load(f)
    candidate=candidate_from_catalog(catalog)
    from slater_research.replay_engine import Clip
    from slater_research.verified_defender_env import VerifiedDefenderEnv
    from rlgym.rocket_league.sim import RocketSimEngine
    sha_before=hashlib.sha256(file_path.read_bytes()).hexdigest()
    clip=Clip.load(file_path)
    if clip.replay_sha!=candidate['replay_sha256']:
        raise ValueError('Clip replay SHA mismatch')
    # Verify replay goal before any intervention. Original goal should be frame 179.
    eng=RocketSimEngine(rlbot_delay=False)
    try:
        base_env=VerifiedDefenderEnv(clip,candidate,eng,train_only=True)
        baseline=base_env.run_reference()
    finally:
        eng.close()
    if (baseline.status!='attacker_goal' or baseline.goal_step!=179 or
        baseline.endpoint_ball_error_uu is None or
        baseline.peak_reference_error_uu is None or
        max(baseline.endpoint_ball_error_uu,baseline.peak_reference_error_uu)>250):
        raise ValueError('Original goal baseline failed; refusing counterfactual extension')
    rows=[]
    for mode in ('repeat_last','neutral'):
        row=run_probe_and_continue(clip,candidate,attacker_mode=mode,extra_seconds=args.extra_seconds)
        rows.append(row)
        print(f"{mode}: original={row['original_window_status']} "
              f"first_touch={row['first_touch_step']} extension={row['extension_status']} "
              f"steps={row['extended_steps']}", flush=True)
    if any(r['first_touch_step']!=176 or r['original_window_status']!='no_goal_by_deadline' for r in rows):
        raise RuntimeError('Successful reactive candidate was NOT reproduced; refusing report')
    if rows[0]['deadline_moment']!=rows[1]['deadline_moment']:
        raise RuntimeError('Two independent initial rollouts diverged before continuation')
    if hashlib.sha256(file_path.read_bytes()).hexdigest()!=sha_before:
        raise RuntimeError('Input NPZ unexpectedly changed')
    result={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
            'purpose':'Read-only exploratory follow-through of first reactive natural-position touch',
            'warning':('Only original goal baseline is replay-verified. Attacker actions AFTER the recorded '
                       'goal are unavailable. An extension with constant-last or neutral attacker '
                       'controls is NOT a replay ground truth, save certification, or training data. '
                       'No checkpoint, PPO, source NPZ, or teacher modification.'),
            'clip_file':CLIP_FILE,'clip_sha256':sha_before,'policy':PROBE.label(),
            'policy_uses_future_replay':False,
            'baseline':{'status':baseline.status,'goal_step':baseline.goal_step,
                        'reference_endpoint_error_uu':baseline.endpoint_ball_error_uu,
                        'peak_reference_error_uu':baseline.peak_reference_error_uu},
            'original_window_deadline':int(candidate['reference_goal_step'])+int(candidate['tail_steps']),
            'extra_seconds_requested':args.extra_seconds,
            'continuations':rows,
            'summary':{'baseline_valid':True,
                       'reactive_touch_reproduced':True,
                       'original_deadline_goal_prevented':True,
                       'extensions_with_attacker_goal':sum(r['extension_status']=='attacker_goal' for r in rows),
                       'extensions_with_no_goal':sum(r['extension_status']=='no_goal_within_exploratory_extension' for r in rows)}}
    out_path.parent.mkdir(parents=True,exist_ok=True)
    partial=out_path.with_name(out_path.name+'.partial')
    with partial.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    os.replace(partial,out_path)
    print('SUMMARY',result['summary'])
    print('READ ONLY. Extended attacker behavior is assumed, NOT replay verified. NOT A CERTIFIED SAVE.')


if __name__=='__main__':
    main()
