"""v0.1.7 read-only defender counterfactual baseline audit.

Use only catalog-verified, short-window training-split goals. Reproduce a
reference goal under fully dynamic physics, then alter *defender inputs only*
with simple fixed probes. A delayed/missing goal under a probe is NOT proof of a
save, defender reachability, or trainability. No checkpoint or original NPZ is
modified, and this module does NOT initiate PPO.

    python -m slater_research.counterfactual_audit \
      --clips data/replay_scenarios_smoke_v012 \
      --catalog data/replay_scenarios_smoke_v012/shot_catalog_v016.json \
      --limit 12 --split train --out data/replay_scenarios_smoke_v012/counterfactual_v017_12.json
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

import numpy as np

from slater_research.replay_engine import Clip, FPS, TICKS, split_replay

PROBES = ('replay', 'neutral', 'brake', 'boost_straight', 'jump_boost')
SHA_RE = re.compile(r'^[a-f0-9]{64}$')


def select_candidates(catalog: dict, split: str = 'train', limit: int = 12) -> list[dict]:
    """Select distinct-source-replay goals first; prioritize closer defenders."""
    if catalog.get('schema_version') != 1:
        raise ValueError('Expected v0.1.6 catalog schema_version=1')
    if split not in ('train', 'validation', 'test', 'all') or limit < 1:
        raise ValueError('Invalid split or limit')
    groups: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for c in catalog.get('candidates', []):
        if split != 'all' and c.get('split') != split:
            continue
        name = c.get('clip_file')
        sha = c.get('replay_sha256')
        if (not isinstance(name, str) or name != Path(name).name or
                not name.endswith('.npz') or not isinstance(sha, str) or
                not SHA_RE.fullmatch(sha)):
            raise ValueError('Invalid catalog filename or replay checksum')
        if name in seen:
            raise ValueError('Duplicate catalog clip name')
        seen.add(name)
        if split_replay(sha) != c.get('split'):
            raise ValueError(f'Split mismatch for {name}')
        start, goal, tail = (int(c[k]) for k in ('start_step', 'reference_goal_step', 'tail_steps'))
        if not (0 <= start < goal and 1 <= tail <= 16):
            raise ValueError('Invalid scenario frame indices or tail')
        groups[sha].append(c)
    for sha in groups:
        groups[sha].sort(key=lambda x: (
            x.get('priority') != 'defender_opportunity_candidate',
            float(x.get('start_min_defender_distance_uu', float('inf'))),
            x['clip_file']))
    # Round robin to avoid repeatedly selecting one long match.
    ordered = sorted(groups)
    chosen = []
    while ordered and len(chosen) < limit:
        next_round = []
        for sha in ordered:
            if groups[sha]:
                chosen.append(groups[sha].pop(0))
                if groups[sha]:
                    next_round.append(sha)
            if len(chosen) >= limit:
                break
        ordered = next_round
    return chosen


def defender_controls(policy: str, original: np.ndarray, *, first: bool) -> np.ndarray:
    """Very simple 8-control probes, not expert defense or a policy search.

    RocketSim control order: throttle, steer, pitch, yaw, roll, jump, boost, handbrake.
    """
    if policy not in PROBES:
        raise ValueError(f'Unknown probe {policy}')
    original = np.asarray(original, dtype=np.float32)
    if original.shape != (8,) or not np.isfinite(original).all():
        raise ValueError('Invalid reference controls')
    if policy == 'replay':
        return original.copy()
    out = np.zeros(8, dtype=np.float32)
    if policy == 'brake':
        out[0] = -1.
    elif policy in ('boost_straight', 'jump_boost'):
        out[0], out[6] = 1., 1.
        if policy == 'jump_boost' and first:
            out[5] = 1.
    return out


def validate_candidate(candidate: dict, clip: Clip) -> tuple[int, int, int, tuple[int, ...], bool]:
    sha = str(candidate['replay_sha256'])
    if clip.replay_sha != sha or split_replay(sha) != candidate['split']:
        raise ValueError('NPZ replay SHA or split does not match catalog')
    start = int(candidate['start_step'])
    goal = int(candidate['reference_goal_step'])
    tail = int(candidate['tail_steps'])
    if not 0 <= start < goal == clip.goal_step < len(clip.snapshots):
        raise ValueError('NPZ does not contain the catalog reference window')
    if not 1 <= tail <= 16 or not len(clip.ids) in (2, 4, 6):
        raise ValueError('Unsupported tail or roster')
    shooter_orange = bool(clip.snapshots[start].cars[clip.shooter_id].is_orange)
    defenders = tuple(a for a in clip.ids if bool(clip.snapshots[start].cars[a].is_orange) != shooter_orange)
    if not defenders:
        raise ValueError('No defenders in selected goal')
    return start, goal, tail, defenders, shooter_orange


def simulate(clip: Clip, candidate: dict, policy: str, *, engine,
             max_error_uu: float = 250.) -> dict:
    """Run all-dynamic physics with reference attacker, original or probed defender.

    An engine is supplied for tests; production passes a fresh RocketSimEngine.
    Copies initial replay state to ensure independence between simulations.
    """
    start, goal, tail, defenders, attacker_orange = validate_candidate(candidate, clip)
    if policy not in PROBES:
        raise ValueError(policy)
    state = engine.set_state(copy.deepcopy(clip.snapshots[start]), {})
    errs = []
    endpoint_error = None
    goal_step = None
    scored_attack = False
    scored_defense = False
    endpoint_ball = None
    max_until = goal + tail
    for i in range(start, max_until):
        # Match v0.1.5 baseline exactly at the saved endpoint and post-tail:
        # final inferred controls remain constant in the post-window tail.
        action_idx = min(i, goal)
        cmds = {}
        for j, aid in enumerate(clip.ids):
            original = np.asarray(clip.controls[action_idx, j], dtype=np.float32)
            action = (defender_controls(policy, original, first=(i == start))
                      if aid in defenders else original)
            cmds[aid] = np.tile(action, (TICKS, 1))
        state = engine.step(cmds, {})
        current_step = i + 1
        if current_step <= goal:
            reference = clip.snapshots[current_step].ball.position
            e = float(np.linalg.norm(np.asarray(state.ball.position, float) - np.asarray(reference, float)))
            errs.append(e)
            if current_step == goal:
                endpoint_error = e
                endpoint_ball = [float(x) for x in state.ball.position]
        if bool(state.goal_scored):
            goal_step = current_step
            scored_attack = bool(state.ball.position[1] > 0) != attacker_orange
            scored_defense = not scored_attack
            break
    # Missing endpoint indicates an early score and cannot be called faithful.
    max_error = max(errs) if errs else None
    return {
        'policy': policy,
        'goal_step': goal_step,
        'goal_offset_s': (goal_step - goal) * TICKS / FPS if goal_step is not None else None,
        'attacker_scored': bool(scored_attack),
        'defender_scored': bool(scored_defense),
        'endpoint_error_uu': endpoint_error,
        'peak_reference_error_uu': max_error,
        'endpoint_ball_xyz': endpoint_ball,
        'baseline_fidelity_pass': bool(
            policy == 'replay' and goal_step is not None and goal_step >= goal
            and scored_attack and endpoint_error is not None and max_error is not None
            and math.isfinite(endpoint_error) and math.isfinite(max_error)
            and max(endpoint_error, max_error) <= max_error_uu
        ),
    }


def compare_probe(reference: dict, probe: dict) -> dict:
    """Conservative comparative statistics; do not label absent goal a 'save'."""
    if not reference['baseline_fidelity_pass']:
        raise ValueError('Cannot interpret counterfactual without a valid baseline')
    diversion = None
    if reference['endpoint_ball_xyz'] is not None and probe['endpoint_ball_xyz'] is not None:
        diversion = float(np.linalg.norm(
            np.asarray(reference['endpoint_ball_xyz']) - np.asarray(probe['endpoint_ball_xyz'])))
    return {
        **probe,
        'goal_outcome_changed_by_deadline': bool(not probe['attacker_scored']),
        'endpoint_diversion_from_baseline_uu': diversion,
        'interpretation': ('attacker_goal_not_observed_by_deadline' if not probe['attacker_scored']
                           else 'attacker_goal_still_scored'),
    }


def audit_candidate(candidate: dict, clip: Clip, *, max_error_uu: float = 250.,
                    engine_factory=None, probes=PROBES) -> dict:
    if engine_factory is None:
        from rlgym.rocket_league.sim import RocketSimEngine
        engine_factory = lambda: RocketSimEngine(rlbot_delay=False)
    if not probes or probes[0] != 'replay' or len(set(probes)) != len(probes):
        raise ValueError('First probe must be replay positive control, no duplicates')
    output = {'file': candidate['clip_file'], 'split': candidate['split'],
              'window_s': candidate['window_s'], 'replay_sha256': candidate['replay_sha256'],
              'defender_initial_distance_uu': candidate['start_min_defender_distance_uu'],
              'probes': []}
    start, goal, tail, defenders, orange = validate_candidate(candidate, clip)
    output.update({'start_step': start, 'reference_goal_step': goal, 'tail_steps': tail,
                   'defender_ids': list(defenders), 'attacker_orange': orange})
    baseline = None
    for policy in probes:
        engine = engine_factory()
        try:
            result = simulate(clip, candidate, policy, engine=engine, max_error_uu=max_error_uu)
        finally:
            engine.close()
        if baseline is None:
            baseline = result
            output['positive_control_valid'] = result['baseline_fidelity_pass']
            output['probes'].append(result)
            if not output['positive_control_valid']:
                output['status'] = 'baseline_not_reproduced'
                return output
        else:
            output['probes'].append(compare_probe(baseline, result))
    output['status'] = 'counterfactuals_evaluated'
    output['changed_outcome_probes'] = sum(bool(p.get('goal_outcome_changed_by_deadline'))
                                            for p in output['probes'][1:])
    return output


def run_report(clips: Path, catalog: dict, *, limit: int = 12, split: str = 'train',
               max_error: float = 250., engine_factory=None, progress=print) -> dict:
    if not clips.is_dir():
        raise FileNotFoundError(clips)
    candidates = select_candidates(catalog, split, limit)
    cases = []
    for i, candidate in enumerate(candidates, 1):
        name = candidate['clip_file']
        item = {'file': name, 'split': candidate['split']}
        try:
            clip = Clip.load(clips / name)
            item = audit_candidate(candidate, clip, max_error_uu=max_error,
                                   engine_factory=engine_factory)
        except Exception as exc:
            item.update({'status': 'error', 'error': f'{type(exc).__name__}: {exc}'})
        cases.append(item)
        progress(f'[{i}/{len(candidates)}] {name} status={item["status"]} '
                 f'changed_probes={item.get("changed_outcome_probes", "-")} '
                 f'error={item.get("error", "-")}', flush=True)
    ok = [x for x in cases if x['status'] == 'counterfactuals_evaluated']
    return {
        'schema_version': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only counterfactual defender probes for verified short-window goals',
        'warning': 'Probe outcome changes are NOT validated saves, training success, or proof of reachability. '
                   'Only the original replay (replay) is a fidelity control. Holdout splits must not be tuned on.',
        'split': split,
        'policies': list(PROBES),
        'summary': {
            'selected': len(candidates),
            'reproduced_baselines': len(ok),
            'baseline_failures': sum(x['status'] == 'baseline_not_reproduced' for x in cases),
            'exceptions': sum(x['status'] == 'error' for x in cases),
            'changed_outcome_trials': sum(x['changed_outcome_probes'] for x in ok),
            'changed_outcome_clips': sum(x['changed_outcome_probes'] > 0 for x in ok),
            'probe_trials': sum(len(x['probes'])-1 for x in ok),
        },
        'cases': cases,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips', required=True)
    p.add_argument('--catalog', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--split', choices=('train', 'validation', 'test', 'all'), default='train')
    p.add_argument('--limit', type=int, default=12)
    p.add_argument('--max-error', type=float, default=250.)
    args = p.parse_args(argv)
    if args.limit < 1 or not math.isfinite(args.max_error) or args.max_error <= 0:
        p.error('Invalid --limit or --max-error')
    destination = Path(args.out)
    if destination.exists() or destination.with_name(destination.name+'.partial').exists():
        p.error('Output or partial file already exists: will not overwrite')
    catalog_path = Path(args.catalog)
    with catalog_path.open('r', encoding='utf-8') as f:
        catalog = json.load(f)
    results = run_report(Path(args.clips), catalog, limit=args.limit, split=args.split,
                         max_error=args.max_error)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.partial')
    with partial.open('x', encoding='utf-8') as f:
        json.dump(results, f, indent=2, allow_nan=False)
    os.replace(partial, destination)
    print('SUMMARY ' + str(results['summary']))
    print('READ-ONLY: no PPO, original clips, Cycle 9 or champion checkpoint changes.')
    print('Do NOT train until a tail-aware defender environment and held-out baselines pass.')
    return results


if __name__ == '__main__':
    main()
