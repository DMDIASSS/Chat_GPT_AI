"""Read-only short-horizon diagnostic for replay-derived RocketSim shots.

Compares starting 0.25/0.5/1/2 seconds before a replay goal. Runs the same
recorded approximate controls under two *different* simulation assumptions:
  ghosted: attacker is re-positioned from reference, defenders fully dynamic;
  all_dynamic: all cars simulate from the restart without teleports.

Neither result proves that historical car inputs were reconstructed correctly.
No checkpoints/policies/PPO are imported, loaded, or written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from slater_research.replay_engine import Clip, FPS, TICKS, TwoPhaseScenario, split_replay


def choose_diverse_clips(folder: Path, limit: int, split: str = 'all') -> list[Path]:
    """Select one clip per replay before filling remaining slots.

    Avoids auditing the first 5 goals of a *single* replay and mistaking them
    for a representative sample. Only reads each NPZ's replay SHA field.
    """
    if limit <= 0:
        raise ValueError('--limit must be positive')
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    groups = {}
    for file in sorted(folder.glob('*.npz')):
        with np.load(file, allow_pickle=False) as data:
            sha = str(data['replay_sha'])
        if split == 'all' or split_replay(sha) == split:
            groups.setdefault(sha, []).append(file)
    if not groups:
        raise ValueError('No matching .npz clips found')
    # File order is stable; the first round-robin pass maximizes replay diversity.
    paths = []
    while len(paths) < limit and any(groups.values()):
        for sha in sorted(groups):
            if groups[sha] and len(paths) < limit:
                paths.append(groups[sha].pop(0))
    return paths


def review_goal_outcome(*, reference_goal_step: int, stopped_step: int,
                        actual_goal_step: int | None, correct_goal: bool,
                        stopped_error: float | None, goal_frame_error: float | None,
                        max_error: float) -> dict:
    """An early goal can't be compared at the reference goal frame.

    This is deliberately stricter than saying 'scored=True' is a fidelity pass.
    """
    early = actual_goal_step is not None and actual_goal_step < reference_goal_step
    reached = stopped_step >= reference_goal_step
    accepted = bool(correct_goal and not early and reached
                    and goal_frame_error is not None
                    and math.isfinite(goal_frame_error)
                    and goal_frame_error <= max_error)
    return {
        'accepted': accepted,
        'scored_as_reference': bool(correct_goal),
        'early_goal_unverifiable': bool(early),
        'reached_reference_goal_frame': bool(reached),
        'actual_goal_step': actual_goal_step,
        'ball_error_uu_at_reference_goal': goal_frame_error,
        'ball_error_uu_at_stop': stopped_error,
    }


def run_window(clip: Clip, window: float, mode: str, max_error: float = 250.) -> dict:
    """Start near the goal and simulate *only until the reference goal frame*.

    No ball teleportation occurs during rollout. In ghosted mode only the
    non-learner attacker car is reset on each action boundary by the original
    TwoPhaseScenario; in all_dynamic mode no entities are teleported at all.
    """
    if mode not in ('ghosted', 'all_dynamic'):
        raise ValueError(mode)
    if window <= 0 or not math.isfinite(window):
        raise ValueError('Window must be a positive finite number')
    # Reference goal step is the last sample at/before annotated goal time.
    target_idx = min(int(clip.goal_step), len(clip.snapshots) - 1)
    start_idx = max(0, target_idx - max(1, math.ceil(window * FPS / TICKS)))
    if start_idx >= target_idx:
        return {'window_s': window, 'mode': mode, 'error': 'No pre-goal reference frame'}
    attackers_orange = clip.snapshots[start_idx].cars[clip.shooter_id].is_orange
    defenders = [aid for aid in clip.ids
                 if clip.snapshots[start_idx].cars[aid].is_orange != attackers_orange]
    if not defenders:
        return {'window_s': window, 'mode': mode, 'error': 'No opposing team'}

    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=False)
    env = None
    results = {
        'window_s': window,
        'mode': mode,
        'start_step': start_idx,
        'reference_goal_step': target_idx,
        'steps_requested': target_idx - start_idx,
        'reference_ball_y_at_goal': float(clip.snapshots[target_idx].ball.position[1]),
    }
    try:
        if mode == 'ghosted':
            env = TwoPhaseScenario(clip, engine, phase='defender', defenders=defenders)
            env.reset(start_step=start_idx)
            state = env.state
        else:
            state = engine.set_state(copy.deepcopy(clip.snapshots[start_idx]), {})
        initial_err = float(np.linalg.norm(
            np.asarray(state.ball.position, dtype=float) -
            np.asarray(clip.snapshots[start_idx].ball.position, dtype=float)))
        results['initial_ball_error_uu'] = initial_err
        errors = []
        early_goal_step = None
        correct_goal = False
        stopped_step = start_idx
        for i in range(start_idx, target_idx):
            if mode == 'ghosted':
                controls = {aid: clip.controls[env.i, env.idindex[aid]]
                            for aid in env.learners}
                state, _, done, _ = env.step(controls)
                stopped_step = env.i
            else:
                inputs = {aid: np.tile(np.asarray(clip.controls[i, j], np.float32),
                                       (TICKS, 1))
                          for j, aid in enumerate(clip.ids)}
                state = engine.step(inputs, {})
                stopped_step = i + 1
                done = bool(state.goal_scored)
            err = float(np.linalg.norm(
                np.asarray(state.ball.position, dtype=float) -
                np.asarray(clip.snapshots[stopped_step].ball.position, dtype=float)))
            errors.append(err)
            if state.goal_scored:
                early_goal_step = stopped_step
                blue_scored = bool(state.ball.position[1] > 0)
                correct_goal = (blue_scored != bool(attackers_orange))
                break
            if done:
                break
        goal_frame_error = errors[-1] if stopped_step >= target_idx and errors else None
        results.update(review_goal_outcome(
            reference_goal_step=target_idx,
            stopped_step=stopped_step,
            actual_goal_step=early_goal_step,
            correct_goal=correct_goal,
            stopped_error=errors[-1] if errors else None,
            goal_frame_error=goal_frame_error,
            max_error=max_error,
        ))
        results.update({
            'completed_steps': len(errors),
            'ball_error_uu_after_first_step': errors[0] if errors else None,
            'first_step_above_threshold': next((start_idx+j+1
                                                for j, value in enumerate(errors)
                                                if value > max_error), None),
            'max_ball_error_uu_during_rollout': max(errors, default=None),
            'simulation_ball_y_at_stop': float(state.ball.position[1]),
            'reference_ball_y_at_stop': float(clip.snapshots[stopped_step].ball.position[1]),
            'error': None,
        })
    finally:
        engine.close()
    return results


def run_report(folder: Path, limit: int, windows: list[float], max_error: float,
               split: str = 'all', progress=print) -> dict:
    files = choose_diverse_clips(folder, limit, split)
    cases = []
    for index, file in enumerate(files, 1):
        started = time.perf_counter()
        c = {'file': file.name, 'windows': []}
        try:
            clip = Clip.load(file)
            c.update({'replay_sha256': clip.replay_sha,
                      'roster_size': len(clip.ids),
                      'available_s': round((len(clip.snapshots)-1)*TICKS/FPS, 3),
                      'reference_goal_step': clip.goal_step})
            for window in windows:
                for mode in ('ghosted', 'all_dynamic'):
                    try:
                        diagnostic = run_window(clip, window, mode, max_error=max_error)
                    except Exception as exc:
                        diagnostic = {'window_s': window, 'mode': mode,
                                      'accepted': False,
                                      'error': f'{type(exc).__name__}: {exc}'}
                    c['windows'].append(diagnostic)
                    msg = (f'[{index}/{len(files)}] {file.name} '
                           f'{mode:11s} start={window:g}s '
                           f'scored={diagnostic.get("scored_as_reference", "-")} '
                           f'err_at_ref={diagnostic.get("ball_error_uu_at_reference_goal", "-")} '
                           f'err_at_stop={diagnostic.get("ball_error_uu_at_stop", "-")} '
                           f'early={diagnostic.get("early_goal_unverifiable", "-")} '
                           f'accepted={diagnostic.get("accepted", False)} '
                           f'error={diagnostic.get("error") or "-"}')
                    progress(msg, flush=True)
        except Exception as exc:
            c['load_error'] = f'{type(exc).__name__}: {exc}'
            progress(f'[{index}/{len(files)}] {file.name}: {c["load_error"]}', flush=True)
        c['wall_seconds'] = round(time.perf_counter() - started, 3)
        cases.append(c)
    rows = [w for case in cases for w in case['windows']]
    return {
        'schema_version': 2,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'description': 'Short-horizon exploratory replay fidelity; no PPO or checkpoint mutations',
        'warning': 'Inferred controls and snapshots are approximate. Passing a 0.25 s '
                   'window does not establish whole-shot physical fidelity. '
                   'Goal time in sampled clips can precede the actual score crossing.',
        'threshold_uu': max_error,
        'windows_s': windows,
        'selection': 'round-robin by replay SHA to avoid sampling only one replay',
        'summary': {
            'replays': len({c.get('replay_sha256') for c in cases if c.get('replay_sha256')}),
            'clips': len(cases),
            'window_runs': len(rows),
            'accepted': sum(bool(w.get('accepted')) for w in rows),
            'early_unverifiable': sum(bool(w.get('early_goal_unverifiable')) for w in rows),
            'errors': sum(bool(w.get('error')) for w in rows),
        },
        'cases': cases,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips', required=True)
    p.add_argument('--limit', type=int, default=5)
    p.add_argument('--windows', default='0.25,0.5,1,2')
    p.add_argument('--max-error', type=float, default=250.)
    p.add_argument('--split', choices=('all', 'train', 'validation', 'test'), default='all')
    p.add_argument('--out', required=True, help='New JSON path (never overwrite)')
    args = p.parse_args(argv)
    try:
        windows = sorted(set(float(v.strip()) for v in args.windows.split(',')))
    except ValueError:
        p.error('Invalid --windows. Example: 0.25,0.5,1,2')
    if not windows or not all(math.isfinite(w) and w > 0 for w in windows):
        p.error('--windows must all be finite, positive numbers')
    if not math.isfinite(args.max_error) or args.max_error <= 0:
        p.error('--max-error must be finite and positive')
    if args.limit < 1:
        p.error('--limit must be positive')
    output = Path(args.out)
    if output.exists():
        p.error(f'Existing report will not be overwritten: {output}')
    report = run_report(Path(args.clips), args.limit, windows, args.max_error, args.split)
    # Non-standard Infinity/NaN are intentionally prohibited in JSON reports.
    def safe(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, dict):
            return {key: safe(value) for key, value in v.items()}
        if isinstance(v, list):
            return [safe(item) for item in v]
        return v
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + '.partial')
    with temp.open('w', encoding='utf8') as f:
        json.dump(safe(report), f, indent=2, allow_nan=False)
    os.replace(temp, output)
    print(f"SUMMARY {report['summary']}; report={output}", flush=True)
    print('READ ONLY: no PPO, no source-clip mutation, no Cycle 9 checkpoint modification', flush=True)
    print('Do not train from these data until a viable shot reconstruction method is validated.', flush=True)


if __name__ == '__main__':
    main()
