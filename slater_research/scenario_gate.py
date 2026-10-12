"""v0.1.6: read-only short-shot candidate catalog from goal-tail fidelity reports.

This module NEVER trains or changes any original replay/NPZ/checkpoint. A verified
replay-driven goal is a *positive control* for a defender drill, not proof that a
learning defender can reach the ball. We additionally report simple geometric
opportunity diagnostics without claiming dynamic reachability.

Run after a goal_tail_audit of the complete extracted dataset:
    python -m slater_research.scenario_gate \
        --clips data/replay_scenarios_smoke_v012 \
        --report data/replay_scenarios_smoke_v012/goal_tail_full.json \
        --out data/replay_scenarios_smoke_v012/shot_catalog.json
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from slater_research.replay_engine import FPS, TICKS, split_replay

# rlgym_tools 2.6.x ReplayFrame serializer offsets (v2 schema).
# RF header: 10 fields + agent IDs + update ages + 8 actions/player.
# GameState: 23 fields then 34 boost-pad timers then 46 fields/car;
# car field 0 = agent ID, following 45 values include physics at 27:45.
BOOST_PAD_COUNT = 34
CAR_STATE_SIZE = 46
CARS_OFFSET = 23 + BOOST_PAD_COUNT
CAR_PHYS_POS_OFFSET = 1 + 27
BALL_POS_OFFSET = 5


def _is_verified(row: dict) -> bool:
    if not isinstance(row, dict) or row.get('error'):
        return False
    if not all(row.get(k) is True for k in (
        'accepted', 'endpoint_position_matched',
        'entire_reference_window_matched', 'verified_goal_by_deadline',
        'scored_as_reference_team')):
        return False
    try:
        end_error = float(row['endpoint_ball_error_uu'])
        max_error = float(row['max_reference_window_error_uu'])
        ref_step = int(row['reference_goal_step'])
        goal_step = int(row['actual_goal_step'])
        tail = int(row['post_budget_steps'])
        return bool(
            math.isfinite(end_error) and math.isfinite(max_error)
            and end_error >= 0 and max_error >= 0
            and 0 <= ref_step <= goal_step <= ref_step + tail
            and not row.get('early_goal_unverifiable', False)
        )
    except (KeyError, ValueError, TypeError):
        return False


def verified_pairs(case: dict, *, allowable_windows=(0.5, 1.0)) -> list[dict]:
    """Require independent successful ghosted AND all-dynamic positive controls."""
    by_window: dict[float, dict[str, dict]] = {}
    for row in case.get('windows', []):
        try:
            w = float(row['window_s'])
        except (KeyError, ValueError, TypeError):
            continue
        if not math.isfinite(w) or not any(abs(w - a) < 1e-6 for a in allowable_windows):
            continue
        mode = row.get('mode')
        if mode not in ('ghosted', 'all_dynamic') or not _is_verified(row):
            continue
        by_window.setdefault(w, {})[mode] = row
    result = []
    for w in sorted(by_window):
        modes = by_window[w]
        if set(modes) != {'ghosted', 'all_dynamic'}:
            continue
        g, d = modes['ghosted'], modes['all_dynamic']
        if (g['start_step'] != d['start_step']
                or g['reference_goal_step'] != d['reference_goal_step']):
            continue
        result.append({
            'window_s': w,
            'start_step': int(g['start_step']),
            'reference_goal_step': int(g['reference_goal_step']),
            'ghosted_endpoint_error_uu': float(g['endpoint_ball_error_uu']),
            'dynamic_endpoint_error_uu': float(d['endpoint_ball_error_uu']),
            'ghosted_peak_error_uu': float(g['max_reference_window_error_uu']),
            'dynamic_peak_error_uu': float(d['max_reference_window_error_uu']),
            'tail_steps': max(int(g['post_budget_steps']), int(d['post_budget_steps'])),
            'ghosted_goal_offset_s': float(g['goal_offset_s']),
            'dynamic_goal_offset_s': float(d['goal_offset_s']),
        })
    return result


def geometry_from_npz(path: Path, start_step: int, goal_step: int) -> dict:
    """Compute observed defender-to-ball distances from immutable NPZ snapshots.

    Distance alone is NOT a reachability test (speed, velocity, boosts and
    intercept path still matter). Validates exact v2 serialization shape.
    """
    with np.load(path, allow_pickle=False) as npz:
        ids = npz['agent_ids']
        n = len(ids)
        frames = npz['frames']
        stored_goal = int(npz['goal_step'])
        shooter_id = int(npz['shooter_id'])
        digest = str(npz['replay_sha'])
        tick_size = int(npz['ticks_per_step'])
    if n not in (2, 4, 6) or tick_size != TICKS:
        raise ValueError(f'{path.name}: roster / step size unsupported')
    if list(ids) != list(range(1, n + 1)) or shooter_id not in ids:
        raise ValueError(f'{path.name}: invalid agent ID layout')
    header = 10 + n * 10
    required = header + CARS_OFFSET + n * CAR_STATE_SIZE
    if frames.ndim != 2 or frames.shape[1] != required:
        raise ValueError(f'{path.name}: serializer mismatch ({frames.shape} vs (*,{required}))')
    if stored_goal != goal_step or not 0 <= start_step < goal_step < len(frames):
        raise ValueError(f'{path.name}: inconsistent goal/start index')
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest.lower()):
        raise ValueError(f'{path.name}: invalid replay SHA')
    # A valid overtime replay uses +inf as the scoreboard game timer at RF[0].
    # Reject other NaN/Inf data; do not reject legitimate overtime goals.
    if not np.isfinite(frames[start_step:goal_step+1, 1:]).all():
        raise ValueError(f'{path.name}: non-finite replay data outside overtime game timer')

    shooter = shooter_id - 1
    team_idxs = [header + CARS_OFFSET + j * CAR_STATE_SIZE + 1
                 for j in range(n)]
    shooter_team = int(frames[start_step, team_idxs[shooter]])
    defenders = [j for j in range(n) if int(frames[start_step, team_idxs[j]]) != shooter_team]
    if not defenders:
        raise ValueError(f'{path.name}: no opposing players')
    slice_ = frames[start_step:goal_step+1]
    ball = slice_[:, header + BALL_POS_OFFSET:header + BALL_POS_OFFSET+3]
    distances = []
    start_distances = []
    for j in defenders:
        car_offset = header + CARS_OFFSET + j * CAR_STATE_SIZE + CAR_PHYS_POS_OFFSET
        car = slice_[:, car_offset:car_offset+3]
        dist = np.linalg.norm(ball - car, axis=1)
        distances.append(float(dist.min()))
        start_distances.append(float(dist[0]))
    return {
        'roster_size': n,
        'defender_count': len(defenders),
        'start_min_defender_distance_uu': round(min(start_distances), 1),
        'reference_min_defender_distance_uu': round(min(distances), 1),
        'replay_sha256': digest,
        'shot_direction': 'orange_attacking' if shooter_team == 1 else 'blue_attacking',
    }


def build_catalog(clips: Path, report: dict, *, windows=(0.5, 1.0),
                  max_initial_distance=2500., max_nearest_distance=750.) -> dict:
    if int(report.get('schema_version', -1)) != 3:
        raise ValueError('Require v0.1.5 goal-tail report schema_version=3')
    if not clips.is_dir():
        raise FileNotFoundError(clips)
    if not windows or not all(math.isfinite(x) and x > 0 for x in windows):
        raise ValueError('Invalid window configuration')
    result=[]
    rejections=Counter()
    for case in report.get('cases', []):
        filename=case.get('file', '')
        if Path(filename).name != filename or not filename.endswith('.npz'):
            rejections['invalid_filename']+=1
            continue
        path = clips / filename
        if not path.is_file():
            rejections['missing_clip']+=1
            continue
        pairs = verified_pairs(case, allowable_windows=windows)
        if not pairs:
            rejections['no_both_mode_verified_window']+=1
            continue
        selected = max(pairs, key=lambda x:x['window_s'])
        try:
            geom=geometry_from_npz(path, selected['start_step'], selected['reference_goal_step'])
            if geom['replay_sha256'] != case.get('replay_sha256'):
                raise ValueError('Report / NPZ replay SHA mismatch')
        except Exception as exc:
            rejections[f'bad_npz:{type(exc).__name__}']+=1
            continue
        # These are only heuristic training priority categories, not physical
        # impossibility/possibility claims.
        is_near=(geom['start_min_defender_distance_uu'] <= max_initial_distance or
                 geom['reference_min_defender_distance_uu'] <= max_nearest_distance)
        result.append({
            'clip_file': filename,
            'split': split_replay(geom['replay_sha256']),
            **selected,
            **geom,
            'priority': 'defender_opportunity_candidate' if is_near else 'remote_defender_reference',
            'verified_window_count': len(pairs),
            'warning': 'Baseline scored with replay controls only. Counterfactual defender-policy results are NOT validated.',
        })
    if not result:
        rejections['no_verified_candidates']=1
    by_split=Counter(x['split'] for x in result)
    by_priority=Counter(x['priority'] for x in result)
    return {
        'schema_version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_report_schema_version': 3,
        'method': 'dual-mode, short-window goal-tail positive-control gate',
        'windows_allowed_s': list(windows),
        'max_initial_distance_uu': max_initial_distance,
        'max_nearest_distance_uu': max_nearest_distance,
        'warning': 'READ ONLY. Candidate selection is NOT a PPO-training certification. Original trainer terminates before goal tail; update it before using these windows.',
        'summary': {
            'report_cases': len(report.get('cases', [])),
            'verified_clip_count': len(result),
            'train_count': by_split['train'],
            'validation_count': by_split['validation'],
            'test_count': by_split['test'],
            'defender_opportunity_candidates': by_priority['defender_opportunity_candidate'],
            'remote_defender_references': by_priority['remote_defender_reference'],
            'rejections': dict(rejections),
        },
        'candidates': result,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips', required=True)
    p.add_argument('--report',required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--windows',default='0.5,1')
    p.add_argument('--max-initial-distance', type=float,default=2500.)
    p.add_argument('--max-nearest-distance', type=float,default=750.)
    a=p.parse_args(argv)
    output=Path(a.out)
    if output.exists():p.error('Refusing to overwrite existing report')
    try:
        ws=sorted(set(float(s) for s in a.windows.split(',')))
    except ValueError:p.error('Invalid --windows')
    if not ws or not all(math.isfinite(x) and x>0 for x in ws):p.error('Invalid --windows')
    if not all(math.isfinite(x) and x>0 for x in (a.max_initial_distance,a.max_nearest_distance)):
        p.error('Distance limits must be finite and positive')
    report_path=Path(a.report)
    with report_path.open('r',encoding='utf8') as f:report=json.load(f)
    catalog=build_catalog(Path(a.clips),report,windows=ws,
                          max_initial_distance=a.max_initial_distance,
                          max_nearest_distance=a.max_nearest_distance)
    catalog['source_report_sha256']=hashlib.sha256(report_path.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.name+'.partial')
    if temporary.exists():p.error('Partial report already exists; clear it manually')
    with temporary.open('x',encoding='utf8') as f:
        json.dump(catalog,f,indent=2,allow_nan=False)
    os.replace(temporary,output)
    print('SUMMARY '+str(catalog['summary']))
    print('WROTE '+str(output))
    print('READ ONLY: no simulator mutation, PPO, or checkpoint modification')
    print('DO NOT TRAIN YET: scenario tail and counterfactual baselines are not yet wired into the PPO trainer')
    return catalog

if __name__=='__main__':main()
