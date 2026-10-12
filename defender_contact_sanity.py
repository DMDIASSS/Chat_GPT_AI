r"""Read-only contact sanity test for Slater replay defenders.

Uses verified TRAIN replay-control goals as positive controls, then resets the
same RocketSim scene with its defender pre-positioned *once* on a recorded
future ball path. Those placements are intentionally synthetic, physically
implausible as a skill baseline, and must NEVER be labelled replay saves.

The purpose is to check that a real RocketSim car/ball collision can occur in
these short windows. Nothing in this file trains or edits any source scenario.

Usage in Windows CMD:
  .venv\Scripts\python.exe defender_contact_sanity.py --clips data\replay_scenarios_carfix_v020_12 --catalog data\replay_scenarios_carfix_v020_12\catalog_repaired_v020_11.json --out data\replay_scenarios_carfix_v020_12\contact_sanity_v020.json
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

import numpy as np

TICKS = 8
FPS = 120
GOAL_ERROR_THRESHOLD_UU = 250.0


def xyz(v):
    out = np.asarray(v, dtype=float).reshape(3)
    if not np.isfinite(out).all():
        raise ValueError('Nonfinite 3D vector')
    return out


def plan_targets(clip, candidate, *, max_targets=3):
    """Select reproducible lab-only intercept spots. No gameplay policy uses future frames."""
    start = int(candidate['start_step'])
    goal = int(candidate['reference_goal_step'])
    if not (0 <= start < goal < len(clip.snapshots)):
        raise ValueError('Invalid window indices')
    shooter = clip.shooter_id
    start_ball = xyz(clip.snapshots[start].ball.position)
    attacker = xyz(clip.snapshots[start].cars[shooter].physics.position)
    proposals = []
    for k in range(2, min(9, goal - start)):
        target = xyz(clip.snapshots[start + k].ball.position)
        start_separation = float(np.linalg.norm(target - start_ball))
        attacker_separation = float(np.linalg.norm(target - attacker))
        if (start_separation < 300 or attacker_separation < 250 or
                abs(float(target[0])) > 3900 or abs(float(target[1])) > 5000 or
                not (75 <= target[2] <= 1850)):
            continue
        proposals.append({
            'future_step_offset': k,
            'future_seconds': round(k * TICKS / FPS, 5),
            'synthetic_defender_xyz': target.tolist(),
            'start_ball_distance_uu': round(start_separation, 2),
            'start_attacker_distance_uu': round(attacker_separation, 2),
        })
    if len(proposals) > max_targets:
        indices = np.linspace(0, len(proposals) - 1, num=max_targets).round().astype(int)
        proposals = [proposals[int(i)] for i in indices]
    return proposals


def make_synthetic_car_state(car, target):
    """Set an artificial stationary car in the ball's future path, once at reset."""
    if car.is_demoed or car.demo_respawn_timer > 0:
        raise ValueError('Refuse to revive a demolished defender')
    car.physics.position = xyz(target).astype(np.float32)
    car.physics.linear_velocity = np.zeros(3, dtype=np.float32)
    car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
    car.physics.rotation_mtx = np.eye(3, dtype=np.float32)
    car.wheels_with_contact = (False, False, False, False)
    car.is_jumping = False
    car.has_jumped = False
    car.is_holding_jump = False
    car.has_double_jumped = False
    car.has_flipped = False
    car.air_time_since_jump = 0.0
    car.jump_time = 0.0
    car.flip_time = 0.0
    car.is_autoflipping = False
    car.autoflip_timer = 0.0
    return car


def run_once(clip, candidate, factory, *, defender_id: int, target=None):
    """All cars are dynamic, no mid-simulation teleportation. New engine per run."""
    engine = factory()
    try:
        start = int(candidate['start_step'])
        goal = int(candidate['reference_goal_step'])
        tail = int(candidate.get('tail_steps', 4))
        if tail < 0 or tail > 16:
            raise ValueError('Invalid tail length')
        baseline = target is None
        state = copy.deepcopy(clip.snapshots[start])
        if not baseline:
            make_synthetic_car_state(state.cars[defender_id], target)
        state = engine.set_state(state, {})
        initial_defender_xyz = xyz(state.cars[defender_id].physics.position).tolist()
        ref_goal_y = float(clip.snapshots[goal].ball.position[1])
        if abs(ref_goal_y) < 3000:
            raise ValueError('Reference goal location is not near a goal')
        reference_sign = 1 if ref_goal_y > 0 else -1
        peak_ball_err = 0.0
        last_ball_err = None
        last_ref_index = None
        touch_steps = []
        scored_step = None
        scoring_sign = None
        min_distance_uu = float('inf')
        final_state = state
        for i in range(start, goal + tail):
            actions = {}
            for ai, aid in enumerate(clip.ids):
                control = np.asarray(clip.controls[min(i, goal), ai], dtype=np.float32)
                if aid == defender_id and not baseline:
                    control = np.zeros(8, dtype=np.float32)  # Stationary lab target
                if control.shape != (8,) or not np.isfinite(control).all():
                    raise ValueError('Bad control vector')
                actions[aid] = np.repeat(control[None, :], TICKS, axis=0)
            final_state = engine.step(actions, {})
            next_step = i + 1
            gap = float(np.linalg.norm(xyz(final_state.cars[defender_id].physics.position) -
                                       xyz(final_state.ball.position)))
            min_distance_uu = min(gap, min_distance_uu)
            if final_state.cars[defender_id].ball_touches:
                touch_steps.append(next_step)
            if next_step <= goal:
                reference_ball = xyz(clip.snapshots[next_step].ball.position)
                ball_error = float(np.linalg.norm(xyz(final_state.ball.position) - reference_ball))
                peak_ball_err = max(peak_ball_err, ball_error)
                if next_step == goal:
                    last_ball_err = ball_error
                    last_ref_index = next_step
            if final_state.goal_scored:
                scored_step = next_step
                scoring_sign = 1 if float(final_state.ball.position[1]) > 0 else -1
                break
        status = ('no_goal_by_deadline' if scored_step is None else
                  'attacker_goal' if scoring_sign == reference_sign else 'other_goal')
        is_baseline_valid = (baseline and status == 'attacker_goal' and
                             scored_step >= goal and last_ref_index == goal and
                             last_ball_err is not None and
                             max(peak_ball_err, last_ball_err) <= GOAL_ERROR_THRESHOLD_UU)
        return {
            'status': status,
            'attacker_scored': status == 'attacker_goal',
            'defender_touch_observed': bool(touch_steps),
            'first_touch_step': touch_steps[0] if touch_steps else None,
            'touch_steps': touch_steps,
            'goal_step': scored_step,
            'goal_offset_s': None if scored_step is None else round((scored_step-goal)*TICKS/FPS, 5),
            'peak_reference_ball_error_uu': round(peak_ball_err, 3),
            'reference_endpoint_error_uu': None if last_ball_err is None else round(last_ball_err, 3),
            'min_car_ball_distance_uu': round(min_distance_uu, 2),
            'initial_defender_xyz': initial_defender_xyz,
            'final_defender_xyz': xyz(final_state.cars[defender_id].physics.position).tolist(),
            'baseline_accepted': is_baseline_valid if baseline else None,
        }
    finally:
        engine.close()


def evaluate_one(clip, candidate, factory):
    if candidate.get('split') != 'train':
        raise ValueError('Holdout split cannot be used in diagnostic')
    if clip.replay_sha != candidate['replay_sha256']:
        raise ValueError('Replay SHA mismatch')
    if len(clip.ids) != 2:
        raise ValueError('Only 1v1 diagnostics supported')
    defenders = [aid for aid in clip.ids if aid != clip.shooter_id]
    defender = defenders[0]
    if clip.snapshots[int(candidate['start_step'])].cars[defender].is_demoed:
        return {'status': 'skipped_demolished', 'clip_file': candidate['clip_file']}
    baseline = run_once(clip, candidate, factory, defender_id=defender)
    report = {'clip_file': candidate['clip_file'], 'status': 'baseline_failed',
              'baseline': baseline, 'placements': []}
    if not baseline['baseline_accepted']:
        return report
    report['status'] = 'tested'
    for placement in plan_targets(clip, candidate):
        synthetic = run_once(clip, candidate, factory,
                             defender_id=defender, target=placement['synthetic_defender_xyz'])
        report['placements'].append({**placement, **synthetic,
                                     'touch_and_no_goal_by_deadline': (
                                         synthetic['defender_touch_observed'] and
                                         synthetic['status'] == 'no_goal_by_deadline')})
    if not report['placements']:
        report['status'] = 'no_valid_target_geometry'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips', required=True)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--limit', type=int, default=11)
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error('--limit must be positive')
    clips_dir, dst = Path(args.clips), Path(args.out)
    if not clips_dir.is_dir():
        parser.error(f'Missing directory: {clips_dir}')
    if dst.exists() or dst.with_name(dst.name+'.partial').exists():
        parser.error('Output or partial file exists; refusing to overwrite')
    with open(args.catalog, encoding='utf-8') as f:
        catalog = json.load(f)
    candidates = [c for c in catalog['candidates'] if c['split'] == 'train'][:args.limit]
    from slater_research.replay_engine import Clip
    from rlgym.rocket_league.sim import RocketSimEngine
    factory = lambda: RocketSimEngine(rlbot_delay=False)
    cases = []
    for index, candidate in enumerate(candidates, 1):
        try:
            clip = Clip.load(clips_dir / candidate['clip_file'])
            row = evaluate_one(clip, candidate, factory)
        except Exception as exc:
            row = {'clip_file': candidate['clip_file'], 'status': 'error',
                   'error': f'{type(exc).__name__}: {exc}'}
        cases.append(row)
        touches = sum(bool(p.get('defender_touch_observed')) for p in row.get('placements', []))
        print(f'[{index}/{len(candidates)}] {candidate["clip_file"]}: '
              f'{row["status"]}, synthetic_touches={touches}/{len(row.get("placements", []))}', flush=True)
    good = [r for r in cases if r['status'] in ('tested', 'no_valid_target_geometry')]
    trials = [p for r in good for p in r['placements']]
    report = {
        'schema_version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Synthetic stationary defender collision sanity test; not a real save or training input',
        'warning': ('Defender is artificially placed on FUTURE recorded ball flight before simulation. '
                    'This is physics instrumentation, not a feasible policy, honest defense scenario, or training data. '
                    'Goal timeout is not a confirmed save. Train split only.'),
        'summary': {
            'selected': len(candidates),
            'valid_replay_baselines': len(good),
            'baseline_failures': sum(x['status'] == 'baseline_failed' for x in cases),
            'skipped_demolished': sum(x['status'] == 'skipped_demolished' for x in cases),
            'errors': sum(x['status'] == 'error' for x in cases),
            'synthetic_placement_trials': len(trials),
            'synthetic_touch_trials': sum(x['defender_touch_observed'] for x in trials),
            'synthetic_touch_and_no_goal_by_deadline': sum(x['touch_and_no_goal_by_deadline'] for x in trials),
        }, 'cases': cases,
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name+'.partial')
    with temp.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    os.replace(temp, dst)
    print('SUMMARY', report['summary'])
    print('READ ONLY. Synthetic placement is a collider sanity check, never an actual save or training datum.')


if __name__ == '__main__':
    main()
