"""v0.2.0 - controlled, reversible repair of stale replay-derived defender flags.

Works on the serialized NPZ layout used by RLGym Tools v2.6.5. Requires
NumPy but does not import RocketSim. No source NPZ, replay, teacher, or
checkpoint is modified. The *new* NPZ files are unverified proposals until
an independent RocketSim goal_tail_audit succeeds again.

Default jump_only is intentionally narrow: clear inconsistent jump/held-jump
flags only where the inferred jump controller is zero for adjacent samples.
An opt-in ground_heuristic mode also repairs obvious flat-floor contacts;
this is inherently speculative and requires a separate physics re-audit.
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

FRAME_FIXED_HEADER = 10
CONTROLS_PER_CAR = 8
BOOST_PAD_COUNT = 34
GAMESTATE_HEADER = 23
CAR_SIZE = 46  # agent_id + 45 serialized Car values
BODY_SIZE = 45
REQUIRED = ('frames', 'controls', 'agent_ids', 'shooter_id', 'goal_step',
            'ticks_per_step', 'replay_sha')


def car_body_start(n: int, index: int) -> int:
    if n not in (2, 4, 6) or not (0 <= index < n):
        raise ValueError('Unsupported roster or car index')
    return FRAME_FIXED_HEADER + 10 * n + GAMESTATE_HEADER + BOOST_PAD_COUNT + index * CAR_SIZE + 1


def validate_clip_arrays(items: dict) -> tuple[int, int]:
    missing = [k for k in REQUIRED if k not in items]
    if missing:
        raise ValueError(f'Missing NPZ keys: {missing}')
    ids = np.asarray(items['agent_ids'])
    n = len(ids)
    frames = np.asarray(items['frames'])
    controls = np.asarray(items['controls'])
    shooter_id = int(items['shooter_id'])
    goal = int(items['goal_step'])
    sha = str(items['replay_sha'])
    if n not in (2, 4, 6) or ids.tolist() != list(range(1, n + 1)):
        raise ValueError('Require sequential RLGym agent ids and 1v1/2v2/3v3')
    if shooter_id not in ids:
        raise ValueError('Shooter not in the roster')
    if int(items['ticks_per_step']) != 8:
        raise ValueError('Require 8 physics ticks per replay step')
    required_cols = FRAME_FIXED_HEADER + 10 * n + GAMESTATE_HEADER + BOOST_PAD_COUNT + n * CAR_SIZE
    if frames.ndim != 2 or frames.shape[1] != required_cols or not 0 <= goal < len(frames):
        raise ValueError(f'Unsupported frame shape {frames.shape}; want (*, {required_cols})')
    if controls.shape != (len(frames), n, CONTROLS_PER_CAR):
        raise ValueError(f'Invalid controls shape: {controls.shape}')
    if frames.dtype != np.float32 or controls.dtype != np.float32:
        raise ValueError('Require original float32 replay serialization')
    # Scoreboard game_timer may be infinity during overtime. All other numeric
    # payload fields must be finite, as must actions.
    if not np.isfinite(frames[:, 1:]).all() or not np.isfinite(controls).all():
        raise ValueError('Nonfinite physics or controls')
    if len(sha) != 64 or any(ch not in '0123456789abcdef' for ch in sha.lower()):
        raise ValueError('Invalid replay digest')
    for j in range(n):
        base = car_body_start(n, j)
        if not np.all(frames[:, base-1] == j+1):
            raise ValueError('Invalid serialized car ID column')
        teams = frames[:, base]
        if not np.all(np.isin(teams, [0, 1])) or np.any(teams != teams[0]):
            raise ValueError('Invalid or changing team identifier')
    return n, goal


def infer_defenders(frames: np.ndarray, n: int, shooter_id: int) -> list[int]:
    # Returns zero-based car array indices, not agent ids.
    team = int(frames[0, car_body_start(n, shooter_id - 1)])
    result = [j for j in range(n) if int(frames[0, car_body_start(n, j)]) != team]
    if not result:
        raise ValueError('No defender found')
    return result


def stable_no_jump(controls: np.ndarray, j: int, step: int) -> bool:
    # Replay-to-RLGym may shift jump edges by a sample. Require a continuous
    # quiet interval including the preceding sample, and following if present.
    lo = max(0, step-1)
    hi = min(len(controls), step+2)
    return bool(np.all(np.abs(controls[lo:hi, j, 5]) < 0.5))


def flat_floor_candidate(frames: np.ndarray, controls: np.ndarray,
                         base: int, j: int, t: int) -> bool:
    """Optional conservative physics heuristic; not a ground-truth label."""
    if t <= 0 or t >= len(frames)-1:
        return False
    if not stable_no_jump(controls, j, t):
        return False
    a = frames[t, base:base+BODY_SIZE]
    pos = a[27:30]; vel = a[30:33]
    rot = a[36:45].reshape(3, 3)
    prev = frames[t-1, base+27:base+30]
    nxt = frames[t+1, base+27:base+30]
    # Octane-like car origin on flat floor is around 17uu; never auto-project
    # arbitrary wall/ceiling cars. Three snapshots must agree with a low floor.
    return bool(
        a[4] <= 0
        and 15 <= pos[2] <= 24
        and 12 <= prev[2] <= 30 and 12 <= nxt[2] <= 30
        and abs(float(vel[2])) < 75
        and abs(float(pos[0])) < 3300 and abs(float(pos[1])) < 4400
        and float(rot[2, 2]) > 0.965
    )


def repair_arrays(items: dict, *, start_step: int, goal_step: int,
                  mode: str = 'jump_only') -> tuple[dict, dict]:
    """Pure copy transform. Return new arrays + auditable diagnostic counters."""
    if mode not in ('jump_only', 'ground_heuristic'):
        raise ValueError('Invalid repair mode')
    n, goal = validate_clip_arrays(items)
    if int(goal_step) != goal or not (0 <= start_step < goal):
        raise ValueError('Candidate start / goal disagrees with clip metadata')
    output = {k: np.asarray(v).copy() for k, v in items.items()}
    original = np.asarray(items['frames'])
    f = output['frames']
    controls = output['controls']
    defenders = infer_defenders(original, n, int(items['shooter_id']))
    counts = Counter()
    demo_at_start = []
    active = []
    for j in defenders:
        base = car_body_start(n, j)
        if float(original[start_step, base + 4]) > 0:
            demo_at_start.append(j + 1)
            counts['demolished_defenders_skipped'] += 1
            continue
        active.append(j + 1)
        # Modify only selected original goal window; NEVER change attacker.
        for t in range(start_step, goal+1):
            row = f[t, base:base+BODY_SIZE]
            if row[4] > 0:
                counts['demo_frames_skipped'] += 1
                continue
            if not stable_no_jump(controls, j, t):
                counts['active_or_uncertain_jump_frames_skipped'] += 1
                continue
            # Replay converter can carry these two flags indefinitely after a
            # jump ends. Both are safe to clear only for quiet controller spans.
            if row[14] > 0:
                row[14] = 0
                counts['stale_held_jump_cleared'] += 1
            if row[15] > 0:
                row[15] = 0
                counts['stale_is_jumping_cleared'] += 1
            if mode == 'ground_heuristic' and flat_floor_candidate(original, controls, base, j, t):
                if sum(row[5:9]) < 3:
                    row[5:9] = 1
                    counts['ground_contact_frames_repaired'] += 1
                # Reset grounded-only flip/jump values, but leave pose and
                # velocity unchanged; RocketSim may still reject this state.
                for ix in (13, 17, 18, 19, 20):
                    if row[ix] != 0:
                        row[ix] = 0
                        counts['ground_aux_values_reset'] += 1
                if np.any(row[21:24] != 0):
                    row[21:24] = 0
                    counts['ground_aux_values_reset'] += 3
    # No action modification, ball teleportation or physics rewriting.
    if not np.array_equal(items['controls'], output['controls']):
        raise AssertionError('Action labels were modified')
    # Ball and config GameState prefix is held constant across every sample.
    state_header = FRAME_FIXED_HEADER + 10*n
    assert np.array_equal(original[:, :state_header+GAMESTATE_HEADER+BOOST_PAD_COUNT],
                          f[:, :state_header+GAMESTATE_HEADER+BOOST_PAD_COUNT])
    for j in range(n):
        base = car_body_start(n, j)
        assert np.array_equal(original[:, base+27:base+45],f[:, base+27:base+45]), 'Car physics changed'
        if j not in defenders:
            assert np.array_equal(original[:, base:base+BODY_SIZE], f[:, base:base+BODY_SIZE]), 'Attacker changed'
    return output, {
        'defenders': [j+1 for j in defenders],
        'active_defenders_at_start': active,
        'demo_at_start': demo_at_start,
        'start_step': start_step,
        'goal_step': goal,
        'mode': mode,
        'changes': dict(counts),
        'changed_scalar_values': int(np.count_nonzero(f != original)),
        'trainable_candidate': bool(active),
        'warning': 'Heuristic state repair. Must re-run RocketSim fidelity. Not PPO ready.',
    }


def select_train_candidates(catalog: dict, limit: int | None = None) -> list[dict]:
    if int(catalog.get('schema_version', -1)) != 1:
        raise ValueError('Expected v0.1.6 scenario catalog schema=1')
    if limit is not None and limit < 1:
        raise ValueError('Limit must be positive')
    rows = catalog.get('candidates', [])
    selected = [c for c in rows if c.get('split') == 'train'
                and c.get('priority') == 'defender_opportunity_candidate']
    if len({c.get('clip_file') for c in selected}) != len(selected):
        raise ValueError('Duplicate clip names in catalog')
    return selected[:limit]


def process(clips: Path, catalog: dict, out_dir: Path, *,
            mode: str = 'jump_only', limit: int | None = None) -> dict:
    clips = Path(clips); out_dir = Path(out_dir)
    if not clips.is_dir():
        raise FileNotFoundError(clips)
    if out_dir.resolve() == clips.resolve() or clips.resolve() in out_dir.resolve().parents:
        raise ValueError('Output must be separate from original source clips')
    selected = select_train_candidates(catalog, limit)
    if not selected:
        raise ValueError('No train-split opportunity candidates')
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError('Output directory must be new or empty; no overwrites')
    rows=[]
    for idx, candidate in enumerate(selected,1):
        name = candidate['clip_file']
        if Path(name).name != name or not name.endswith('.npz'):
            raise ValueError(f'Unsafe catalog filename: {name!r}')
        src = clips / name
        if not src.is_file():
            raise FileNotFoundError(src)
        with np.load(src, allow_pickle=False) as npz:
            data = {k: npz[k].copy() for k in npz.files}
        if str(data['replay_sha']) != candidate.get('replay_sha256'):
            raise ValueError(f'{name}: catalog/clip hash mismatch')
        # Independently rederive the split; never let a stale/mislabeled
        # catalog accidentally include a holdout replay in repair experiments.
        digest = str(data['replay_sha'])
        if int(digest[:8], 16) % 100 >= 80:
            raise ValueError(f'{name}: actual replay hash is not in training split')
        repaired, details = repair_arrays(data, start_step=int(candidate['start_step']),
                                          goal_step=int(candidate['reference_goal_step']),
                                          mode=mode)
        # Never promote a clip with only demoed defenders as a usable exercise.
        if not details['trainable_candidate']:
            status = 'excluded_all_defenders_demoed'
        elif details['changed_scalar_values'] == 0:
            status = 'unchanged'
        else:
            status = 'pending_fidelity_revalidation'
        # Preserve all original keys; annotate derived output for provenance.
        repaired['state_repair_v020'] = np.array(mode)
        repaired['state_repair_warning'] = np.array(
            'Derived/reconstructed defender state; no validation or training certification')
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / name
        if dst.exists():
            raise FileExistsError(dst)
        # Atomic per-clip write via exclusive partial temp path.
        temp = out_dir / (name + '.partial.npz')
        if temp.exists():
            raise FileExistsError(temp)
        with temp.open('xb') as handle:
            np.savez_compressed(handle, **repaired)
        os.replace(temp, dst)
        row = {'clip_file': name, 'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
               'derived_sha256': hashlib.sha256(dst.read_bytes()).hexdigest(),
               'status': status, **details}
        rows.append(row)
        print(f'[{idx}/{len(selected)}] {name}: {status} '
              f'changes={details["changed_scalar_values"]} demo={len(details["demo_at_start"])}', flush=True)
    summary = dict(Counter(r['status'] for r in rows))
    summary.update({'selected':len(selected),'derived_clips':len(rows),
                    'changed_scalar_values':sum(r['changed_scalar_values'] for r in rows),
                    'original_npz_modified':0})
    return {'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
            'tool':'v0.2.0 conservative defender car-state copy repair',
            'mode':mode,'source_clips':str(clips),'derived_clips':str(out_dir),
            'warning':'NOT TRAINING-READY. Rerun RocketSim goal-tail + separate split-aware baseline checks. '
                      'Only train-split candidates were derived. Original clips/teacher/champion untouched.',
            'summary':summary,'cases':rows}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips', required=True)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--mode', choices=('jump_only','ground_heuristic'), default='jump_only')
    args=parser.parse_args(argv)
    if args.limit < 1:
        parser.error('Limit must be >=1')
    destination=Path(args.report)
    if destination.exists() or destination.with_name(destination.name+'.partial').exists():
        parser.error('Output report exists; choose a fresh name')
    with Path(args.catalog).open('r',encoding='utf8') as handle:
        catalog=json.load(handle)
    result=process(Path(args.clips),catalog,Path(args.out_dir),limit=args.limit,mode=args.mode)
    destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_name(destination.name+'.partial')
    with partial.open('x',encoding='utf8') as handle:
        json.dump(result,handle,indent=2,allow_nan=False)
    os.replace(partial,destination)
    print('SUMMARY',result['summary'])
    print('NOT TRAINING-READY; no original clips, PPO, teacher or champion checkpoint changed')
    return result


if __name__ == '__main__':
    main()
