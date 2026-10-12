"""Read-only RocketSim fidelity audit for replay scenario clips.

This command never loads or writes a learner policy and never launches PPO.
It assesses only whether the existing replay-derived controls recreate the
scoring team's goal in the current, kinematic-ghost research environment.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from slater_research.replay_engine import Clip, counterfactual_goal_check, split_replay


def choose_paths(clip_dir: Path, limit: int, split: str) -> list[Path]:
    if not clip_dir.is_dir():
        raise FileNotFoundError(f"Clip directory not found: {clip_dir}")
    if limit < 1:
        raise ValueError("--limit must be at least 1; audit a small batch first")
    # Replay manifest is JSON, and replay scenarios are NPZ. No need to load
    # the manifest and no chance of accidentally including the manifest file.
    paths = sorted(clip_dir.glob("*.npz"))
    if not paths:
        raise FileNotFoundError(f"No .npz scenario clips in {clip_dir}; extract first")
    if split == 'all':
        return paths[:limit]
    result = []
    for path in paths:
        # This is a cheap peek at SHA only, without decoding the whole replay.
        import numpy as np
        with np.load(path, allow_pickle=False) as data:
            sha = str(data['replay_sha'])
        if split_replay(sha) == split:
            result.append(path)
        if len(result) == limit:
            break
    return result


def audit_one(path: Path, max_ball_error: float) -> dict:
    record: dict = {'file': path.name}
    started = time.perf_counter()
    try:
        clip = Clip.load(path)
        record.update({
            'replay_sha256': clip.replay_sha,
            'split': split_replay(clip.replay_sha),
            'roster_size': len(clip.ids),
            'steps': len(clip.snapshots),
            'duration_seconds': round((len(clip.snapshots) - 1) * 8 / 120, 3),
            'goal_step': clip.goal_step,
        })
        if not 0 <= clip.goal_step < len(clip.snapshots):
            raise ValueError('goal_step out of bounds')
        # Simulate all other cars with replay-derived controls and use those
        # controls for the defender(s) as well. No learning is performed.
        outcome = counterfactual_goal_check(
            clip, max_shot_position_error=max_ball_error
        )
        record.update(outcome)
        record['error'] = None
    except Exception as exc:
        record.update({'accepted': False, 'error': f'{type(exc).__name__}: {exc}'})
    record['wall_seconds'] = round(time.perf_counter() - started, 3)
    return record


def make_report(paths: list[Path], threshold: float, progress=print) -> dict:
    results = []
    for n, path in enumerate(paths, 1):
        record = audit_one(path, threshold)
        results.append(record)
        value = record.get('ball_error_uu_at_goal_frame', '-')
        if isinstance(value, float):
            value = round(value, 2)
        progress(f"[{n}/{len(paths)}] {path.name}: "
                 f"accepted={record['accepted']} "
                 f"scored={record.get('scored_as_reference','-')} "
                 f"ball_error_uu={value} "
                 f"error={record.get('error') or '-'}", flush=True)
    totals = Counter('exception' if r.get('error') else
                     ('pass' if r['accepted'] else 'fidelity_fail')
                     for r in results)
    return {
        'schema_version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Slater replay research; read-only full-clip ghost fidelity audit',
        'physics_warning': 'Approximate inferred replay controls and kinematic ghosts; '
                           'passing is necessary but not sufficient for true physical fidelity.',
        'max_ball_error_uu': threshold,
        'summary': {
            'audited': len(results),
            'passed': totals['pass'],
            'failed_fidelity': totals['fidelity_fail'],
            'exceptions': totals['exception'],
        },
        'cases': results,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips', required=True, help='Directory with extracted .npz clips')
    p.add_argument('--limit', type=int, default=5, help='Max number to audit, default 5')
    p.add_argument('--max-error', type=float, default=250.,
                   help='Maximum ball position deviation (uu) at reference goal step')
    p.add_argument('--split', choices=('all','train','validation','test'), default='all')
    p.add_argument('--out', required=True, help='New JSON report path; never overwrite')
    args = p.parse_args(argv)
    import math
    if not math.isfinite(args.max_error) or args.max_error <= 0:
        p.error('--max-error must be finite and positive')
    output = Path(args.out)
    if output.exists():
        p.error(f'Refusing to overwrite existing report: {output}')
    files = choose_paths(Path(args.clips), args.limit, args.split)
    if not files:
        p.error(f'No clips for split {args.split}')
    report = make_report(files, args.max_error)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + '.partial')
    with temp.open('w', encoding='utf-8') as f:
        # Non-finite JSON numbers, including Infinity, are not portable.
        def sanitize(value):
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {k: sanitize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitize(v) for v in value]
            return value
        json.dump(sanitize(report), f, indent=2, ensure_ascii=False, allow_nan=False)
    os.replace(temp, output)
    print(f"SUMMARY {report['summary']}; report={output}", flush=True)
    if report['summary']['passed'] == 0:
        print('NO FIDELITY PASSES. Do NOT train on these clips. '
              'Inspect the report for trajectory drift / simulation errors.', flush=True)
    print('READ-ONLY AUDIT: no training or checkpoint modification performed.', flush=True)


if __name__ == '__main__':
    main()
