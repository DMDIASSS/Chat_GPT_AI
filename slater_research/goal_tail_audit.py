"""Read-only goal-endpoint-aware audit (v0.1.5) for extracted RL replay clips.

The recorded replay's final sample often PRECEDES RocketSim's goal trigger.
This tool reports reference-trajectory agreement independently, then lets
RocketSim run up to --post-seconds past that sample using last inferred inputs.
No learner, replay, checkpoint, or previously emitted report is modified.

Extra tail steps are ALL DYNAMIC, even in ghosted mode, because there is no
reference pose after the clip endpoint to place kinematic ghosts safely.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from slater_research.flight_audit import choose_diverse_clips
from slater_research.replay_engine import Clip, FPS, TICKS, TwoPhaseScenario, split_replay

GOAL_THRESHOLD_Y = 5215.5  # RLGym standard soccar, absolute Y (not a scoring-plane estimate)


def reference_status(ball_y: float, threshold: float = GOAL_THRESHOLD_Y) -> dict:
    y = float(ball_y)
    if not math.isfinite(y):
        raise ValueError('Non-finite reference ball y')
    return {
        'reference_goal_y': y,
        'goal_threshold_abs_y': float(threshold),
        'reference_beyond_goal_trigger': bool(abs(y) > threshold),
        'y_to_goal_trigger_uu': max(0., float(threshold) - abs(y)),
    }


def grade(*, endpoint_error: float | None, peak_error: float | None,
          max_error: float, early_goal: bool, goal_step: int | None,
          reference_goal_step: int, correct_goal: bool, post_budget_steps: int) -> dict:
    """Require both a verified same-team goal and a matching reference flight.

    A goal AFTER the last recorded reference frame is legitimate only within
    the bounded post-rollout budget. Report endpoint vs trajectory separately.
    """
    endpoint_ok = endpoint_error is not None and math.isfinite(endpoint_error) and endpoint_error <= max_error
    flight_ok = peak_error is not None and math.isfinite(peak_error) and peak_error <= max_error
    timely = (goal_step is not None and
              reference_goal_step <= goal_step <= reference_goal_step + post_budget_steps)
    accepted = bool(endpoint_ok and flight_ok and timely and correct_goal and not early_goal)
    return {
        'endpoint_position_matched': bool(endpoint_ok),
        'entire_reference_window_matched': bool(flight_ok),
        'verified_goal_by_deadline': bool(timely and correct_goal and not early_goal),
        'accepted': accepted,
        'reason': ('early_goal_unverifiable' if early_goal else
                   'trajectory_diverged' if not (endpoint_ok and flight_ok) else
                   'goal_not_verified_in_tail' if not (timely and correct_goal) else
                   'pass'),
    }


def audit_window(clip: Clip, window: float, mode: str, *,
                 post_seconds: float = .3, max_error: float = 250.) -> dict:
    if mode not in ('ghosted', 'all_dynamic'):
        raise ValueError(mode)
    if not (math.isfinite(window) and window > 0):
        raise ValueError('Invalid window')
    if not (math.isfinite(post_seconds) and 0 <= post_seconds <= 1.):
        raise ValueError('Post-rollout must be 0 to 1 seconds')
    if not (math.isfinite(max_error) and max_error > 0):
        raise ValueError('Invalid ball error threshold')
    from rlgym.rocket_league.sim import RocketSimEngine

    idx = min(int(clip.goal_step), len(clip.snapshots) - 1)
    start = max(0, idx - max(1, math.ceil(window * FPS / TICKS)))
    if start >= idx:
        return {'window_s': window, 'mode': mode, 'error': 'No pre-goal frames', 'accepted': False}
    post_budget = int(math.floor(post_seconds * FPS / TICKS + 1e-8))
    attacking_orange = bool(clip.snapshots[start].cars[clip.shooter_id].is_orange)
    defenders = [aid for aid in clip.ids if bool(clip.snapshots[start].cars[aid].is_orange) != attacking_orange]
    if not defenders:
        return {'window_s': window, 'mode': mode, 'error': 'No defenders', 'accepted': False}

    reference_pos = np.asarray(clip.snapshots[idx].ball.position, dtype=float)
    out = {
        'window_s': window, 'mode': mode,
        'start_step': start, 'reference_goal_step': idx,
        'reference_window_steps': idx - start,
        'post_budget_steps': post_budget,
        'post_budget_seconds': post_budget * TICKS / FPS,
        **reference_status(float(reference_pos[1])),
    }
    engine = RocketSimEngine(rlbot_delay=False)
    try:
        if mode == 'ghosted':
            scene = TwoPhaseScenario(clip, engine, phase='defender', defenders=defenders)
            scene.reset(start_step=start)
            state = scene.state
        else:
            scene = None
            state = engine.set_state(copy.deepcopy(clip.snapshots[start]), {})

        initial_err = float(np.linalg.norm(np.asarray(state.ball.position, float) -
                                           np.asarray(clip.snapshots[start].ball.position, float)))
        errs = []
        goal_step = None
        same_team_goal = False
        stopped_step = start
        for i in range(start, idx):
            if scene is not None:
                actions = {aid: clip.controls[scene.i, scene.idindex[aid]] for aid in scene.learners}
                state, _, _, _ = scene.step(actions)
                stopped_step = scene.i
            else:
                commands = {
                    aid: np.tile(np.asarray(clip.controls[i, j], np.float32), (TICKS, 1))
                    for j, aid in enumerate(clip.ids)
                }
                state = engine.step(commands, {})
                stopped_step = i + 1
            e = float(np.linalg.norm(np.asarray(state.ball.position, float) -
                                     np.asarray(clip.snapshots[stopped_step].ball.position, float)))
            errs.append(e)
            if state.goal_scored:
                goal_step = stopped_step
                same_team_goal = (bool(state.ball.position[1] > 0) != attacking_orange)
                break

        reached_endpoint = stopped_step == idx
        endpoint_error = errs[-1] if (errs and reached_endpoint) else None
        end_ball_y = float(state.ball.position[1])
        post_steps_used = 0
        # Never compare additional simulator states against nonexistent reference frames.
        if reached_endpoint and goal_step is None:
            last = np.asarray(clip.controls[idx, :, :], dtype=np.float32)
            last_commands = {aid: np.tile(last[j], (TICKS, 1)) for j, aid in enumerate(clip.ids)}
            for extra in range(1, post_budget+1):
                state = engine.step(last_commands, {})
                post_steps_used = extra
                if state.goal_scored:
                    goal_step = idx+extra
                    same_team_goal = (bool(state.ball.position[1] > 0) != attacking_orange)
                    break

        early = goal_step is not None and goal_step < idx
        rating = grade(endpoint_error=endpoint_error,
                       peak_error=max(errs) if errs else None, max_error=max_error,
                       early_goal=early, goal_step=goal_step,
                       reference_goal_step=idx, correct_goal=same_team_goal,
                       post_budget_steps=post_budget)
        out.update({
            'initial_error_uu': initial_err,
            'max_reference_window_error_uu': max(errs) if errs else None,
            'endpoint_ball_error_uu': endpoint_error,
            'simulation_y_at_reference_endpoint': end_ball_y if reached_endpoint else None,
            'scored_in_reference_window': bool(goal_step is not None and goal_step <= idx),
            'scored_in_post_rollout': bool(goal_step is not None and goal_step > idx),
            'scored_as_reference_team': bool(same_team_goal),
            'early_goal_unverifiable': bool(early),
            'actual_goal_step': goal_step,
            'goal_offset_s': (goal_step-idx)*TICKS/FPS if goal_step is not None else None,
            'post_steps_used': post_steps_used,
            'sim_y_after_tail': float(state.ball.position[1]),
            **rating,
            'error': None,
        })
    finally:
        engine.close()
    return out


def run_report(folder: Path, limit: int, windows: list[float], *,
               post_seconds: float, max_error: float, split: str = 'all', progress=print) -> dict:
    files = choose_diverse_clips(folder, limit, split)
    cases = []
    for i, path in enumerate(files, 1):
        started = time.perf_counter()
        case = {'file': path.name, 'windows': []}
        try:
            clip = Clip.load(path)
            case.update({'replay_sha256': clip.replay_sha,
                         'split': split_replay(clip.replay_sha),
                         'roster_size': len(clip.ids),
                         'goal_step': clip.goal_step,
                         **reference_status(float(clip.snapshots[clip.goal_step].ball.position[1]))})
            for window in windows:
                for mode in ('ghosted', 'all_dynamic'):
                    try:
                        row = audit_window(clip, window, mode, post_seconds=post_seconds, max_error=max_error)
                    except Exception as exc:
                        row = {'window_s': window, 'mode': mode, 'accepted': False,
                               'error': f'{type(exc).__name__}: {exc}'}
                    case['windows'].append(row)
                    progress(f'[{i}/{len(files)}] {path.name} {mode:11s} {window:g}s '
                             f'end_err={row.get("endpoint_ball_error_uu")} '
                             f'flight_ok={row.get("entire_reference_window_matched")} '
                             f'post_goal={row.get("scored_in_post_rollout")} '
                             f'goal_lag={row.get("goal_offset_s")} '
                             f'accepted={row.get("accepted",False)} '
                             f'error={row.get("error") or "-"}', flush=True)
        except Exception as exc:
            case['load_error'] = f'{type(exc).__name__}: {exc}'
        case['wall_seconds'] = round(time.perf_counter() - started, 3)
        cases.append(case)
    rows = [r for c in cases for r in c['windows']]
    return {
        'schema_version': 3,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Goal trigger-aware endpoint and short-horizon flight verification',
        'warning': 'Estimated replay controls; same-team score within tail does not validate 12s replay or 2v2/3v3. '
                   'Late tail steps use constant final inferred controls and fully dynamic cars.',
        'goal_threshold_abs_y': GOAL_THRESHOLD_Y,
        'max_ball_error_uu': max_error,
        'windows_s': windows,
        'post_seconds_requested': post_seconds,
        'selection': 'one distinct replay per first round',
        'summary': {
            'replays': len({c.get('replay_sha256') for c in cases if c.get('replay_sha256')}),
            'clips': len(cases),
            'window_runs': len(rows),
            'endpoint_position_matched': sum(bool(r.get('endpoint_position_matched')) for r in rows),
            'entire_reference_window_matched': sum(bool(r.get('entire_reference_window_matched')) for r in rows),
            'verified_goals_by_deadline': sum(bool(r.get('verified_goal_by_deadline')) for r in rows),
            'accepted': sum(bool(r.get('accepted')) for r in rows),
            'errors': sum(bool(r.get('error')) for r in rows),
        },
        'cases': cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips', required=True)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--windows', default='0.25,0.5,1,2')
    parser.add_argument('--post-seconds', type=float, default=.3)
    parser.add_argument('--max-error', type=float, default=250.)
    parser.add_argument('--split', choices=('all', 'train', 'validation', 'test'), default='all')
    parser.add_argument('--out', required=True)
    a = parser.parse_args(argv)
    if not 0 <= a.post_seconds <= 1 or not math.isfinite(a.post_seconds):
        parser.error('--post-seconds must be finite and between 0 and 1')
    if not a.limit >= 1:
        parser.error('--limit must be >=1')
    if not math.isfinite(a.max_error) or a.max_error <= 0:
        parser.error('--max-error must be finite and positive')
    try:
        windows = sorted(set(float(s.strip()) for s in a.windows.split(',')))
    except ValueError:
        parser.error('Invalid comma-separated --windows')
    if not windows or not all(math.isfinite(v) and v>0 for v in windows):
        parser.error('--windows must be finite and positive')
    outpath=Path(a.out)
    if outpath.exists():
        parser.error(f'Refusing to overwrite: {outpath}')
    report=run_report(Path(a.clips),a.limit,windows,
                      post_seconds=a.post_seconds,max_error=a.max_error,split=a.split)
    outpath.parent.mkdir(parents=True,exist_ok=True)
    temp=outpath.with_name(outpath.name+'.partial')
    def sanitize(data):
        if isinstance(data, (float, np.floating)) and not math.isfinite(float(data)):
            return None
        if isinstance(data, dict):
            return {k: sanitize(v) for k, v in data.items()}
        if isinstance(data, list):
            return [sanitize(v) for v in data]
        return data
    with temp.open('w',encoding='utf8') as f:
        json.dump(sanitize(report),f,indent=2,allow_nan=False)
    os.replace(temp,outpath)
    print('SUMMARY '+str(report['summary']))
    print('READ ONLY — no PPO, checkpoint, or NPZ modification.')
    print('Do not start training until representative scenario goals and defense baselines pass.',flush=True)


if __name__ == '__main__':
    main()
