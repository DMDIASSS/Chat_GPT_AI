"""Read-only attention-contract audits and paired 1..3-car team matches.

The same frozen reference teammates, rivals, starts and colors face both
policies. Reports are exploratory simulator evidence; nothing is promoted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
from slater_mechanics_eval import interval, load_actor
from slater_team_env import FORMATS, TeamEnv, validate_format
from slater_v041_core import atomic_json, process_lock, read_json, sha256
from slater_versatile_eval import EvaluationPaused

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
SIDES = ('blue', 'orange')
SCHEMA = 1
CODE_FILES = ('slater_team_eval.py', 'slater_team_env.py', 'slater_mechanics_eval.py',
              'slater_nexto_scheduler_v038b.py', 'slater_cycle9_native_ppo_v025.py',
              'afk_team_research.py', 'nexto_teacher.py', 'mechanics_scenarios.py',
              'slater_v041_worker.py', 'slater_v041_core.py', 'slater_versatile_env.py',
              'slater_mechanics_env.py', 'slater_versatile_eval.py', 'vendor/nexto/nexto_obs.py')


def parse_formats(value):
    if isinstance(value, str):
        if value.strip().lower() == 'all':
            return FORMATS
        entries = [part.strip().lower().split('v') for part in value.split(',')]
        if any(len(part) != 2 for part in entries):
            raise ValueError('Formats must be comma-separated pairs such as 1v1,2v2,1v3')
        formats = tuple((int(part[0]), int(part[1])) for part in entries)
    else:
        formats = tuple(tuple(part) for part in value)
    for ours, theirs in formats:
        validate_format(ours, theirs)
    if not formats or len(set(formats)) != len(formats):
        raise ValueError('At least one distinct format is required; duplicates are refused')
    return formats


def policy_digest(actor):
    h = hashlib.sha256()
    for name, tensor in sorted(actor.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        h.update(name.encode('utf-8'))
        h.update(str((tuple(value.shape), str(value.dtype))).encode('ascii'))
        h.update(value.reshape(-1).view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


def runtime_identity():
    packages = {}
    for name in ('torch', 'numpy', 'rlgym-rocket-league', 'rocketsim'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = 'not-installed'
    return {'python': platform.python_version(), 'platform': sys.platform,
            'packages': packages, 'torch_threads': torch.get_num_threads()}


def code_identity():
    return {name: sha256(ROOT / name) for name in CODE_FILES}


def verify_identity_files(identity):
    """Check structured path/hash entries recursively without modifying sources."""
    if isinstance(identity, dict):
        if 'path' in identity and 'sha256' in identity:
            path = Path(identity['path'])
            if not path.is_file() or sha256(path) != identity['sha256']:
                raise RuntimeError(f'Evaluation source changed or disappeared: {path}')
        for value in identity.values():
            verify_identity_files(value)
    elif isinstance(identity, (tuple, list)):
        for value in identity:
            verify_identity_files(value)


def greedy(actor, observation):
    device = next(actor.parameters(), torch.empty(0)).device
    with torch.inference_mode():
        return int(base.logits_of(actor, base.to_tensors(observation, device)).argmax(-1).item())


def match(actor, rivals, *, rival, side, seed, seconds, our_size, their_size,
          scripted_student=False, teammate_actor=None):
    """Play the whole clock, resetting after goals instead of first-goal scoring."""
    if side not in SIDES or rival not in rivals:
        raise ValueError('A known frozen rival and blue/orange side are required')
    if not math.isfinite(seconds) or seconds <= 0 or round(seconds * 120) < 1:
        raise ValueError('Match duration must contain at least one physics tick')
    if type(seed) is not int or seed < 0:
        raise ValueError('Seed must be a nonnegative integer')
    env = TeamEnv(rivals, our_size=our_size, their_size=their_size,
                  fixed_side=side, fixed_rival=rival, teammate_actor=teammate_actor,
                  task_name='match', max_seconds=seconds, scripted_student=scripted_student)
    target = round(seconds * 120)
    ticks = episodes = goals_for = goals_against = 0
    scripts = learner_scripts = learner_touches = team_touches = 0
    frozen_calls = frozen_observations = 0
    try:
        obs = env.reset(seed)
        while ticks < target:
            env.max_seconds = (env.tick_count + target - ticks) / 120
            before = env.tick_count
            obs, _, done, info = env.step(greedy(actor, obs))
            elapsed = env.tick_count - before
            if elapsed <= 0 or ticks + elapsed > target:
                raise RuntimeError('Team match clock failed to advance within its exact budget')
            ticks += elapsed
            if done:
                episodes += 1
                goals_for += int(info['outcome'] == 1)
                goals_against += int(info['outcome'] == -1)
                scripts += int(info['script_physics_ticks'])
                learner_scripts += int(info.get('student_script_physics_ticks', 0))
                learner_touches += int(info.get('learner_touch_ticks', 0))
                team_touches += int(info.get('team_touch_ticks', 0))
                frozen_calls += int(info.get('frozen_batch_calls', 0))
                frozen_observations += int(info.get('frozen_observations', 0))
                if ticks < target:
                    obs = env.reset(seed + 7919 * episodes)
    finally:
        env.close()
    return {'rival': rival, 'side': side, 'seed': seed, 'format': validate_format(our_size, their_size),
            'our_size': our_size, 'their_size': their_size, 'seconds': ticks / 120,
            'goals_for': goals_for, 'goals_against': goals_against,
            'goal_diff': goals_for - goals_against, 'episodes': episodes,
            'won': goals_for > goals_against, 'draw': goals_for == goals_against,
            'lost': goals_for < goals_against, 'student_scripted_kickoff': bool(scripted_student),
            'learner_slots': 1, 'frozen_teammate_policy_supplied': teammate_actor is not None,
            'frozen_scripted_kickoff': True, 'script_physics_ticks': scripts,
            'student_script_physics_ticks': learner_scripts, 'learner_touch_ticks': learner_touches,
            'team_touch_ticks': team_touches, 'frozen_batch_calls': frozen_calls,
            'frozen_observations': frozen_observations}


def cell_key(row):
    return row['format'], row['rival'], row['side'], row['seed']


def expected_cells(formats, rivals, seeds, seed_base):
    return {(validate_format(*fmt), rival, side, seed_base + 997 * j)
            for fmt in formats for rival in rivals for side in SIDES for j in range(seeds)}


def validate_records(records, *, formats, rivals, seeds, seed_base, seconds,
                     scripted_student=False, complete=True):
    expected = expected_cells(formats, rivals, seeds, seed_base)
    seen = set()
    for record in records:
        c, r = record['candidate'], record['reference']
        key = cell_key(c)
        if key != cell_key(r):
            raise ValueError('Unmatched team evaluation pair')
        if key in seen:
            raise ValueError('Duplicate team evaluation cell')
        if key not in expected:
            raise ValueError('Unexpected format, rival, color or seed in team evaluation cache')
        for row in (c, r):
            if (row.get('our_size'), row.get('their_size')) != tuple(map(int, row['format'].split('v'))):
                raise ValueError('Evaluation format and car counts disagree')
            if not math.isclose(row['seconds'], round(seconds * 120) / 120, abs_tol=1e-9):
                raise ValueError('Cached match duration does not match the protocol')
            if row.get('student_scripted_kickoff') != bool(scripted_student):
                raise ValueError('Cached learner kickoff mode changed')
            if row.get('frozen_scripted_kickoff') is not True:
                raise ValueError('Frozen policies must retain scripted kickoff')
            if any(type(row[name]) is not int or row[name] < 0 for name in ('goals_for', 'goals_against')):
                raise ValueError('Invalid goal counts in evaluation cache')
            if row['goal_diff'] != row['goals_for'] - row['goals_against']:
                raise ValueError('Cached goal difference disagrees with goals')
        seen.add(key)
    if complete and seen != expected:
        raise ValueError(f'Incomplete paired team evaluation: {len(seen)}/{len(expected)} cells')
    return seen


def summarize(records, *, formats, rivals, seeds, seed_base, seconds, scripted_student=False):
    validate_records(records, formats=formats, rivals=rivals, seeds=seeds,
                     seed_base=seed_base, seconds=seconds, scripted_student=scripted_student)

    def group(rows):
        clustered = {}
        for pair in rows:
            c, r = pair['candidate'], pair['reference']
            delta = (c['goal_diff'] - r['goal_diff']) * 60 / c['seconds']
            clustered.setdefault(c['seed'], []).append(delta)
        values = {seed: float(np.mean(v)) for seed, v in sorted(clustered.items())}
        totals = {}
        for label in ('candidate', 'reference'):
            cells = [p[label] for p in rows]
            totals[label] = {'matches': len(cells), 'goals_for': sum(c['goals_for'] for c in cells),
                             'goals_against': sum(c['goals_against'] for c in cells),
                             'wins': sum(c['goals_for'] > c['goals_against'] for c in cells),
                             'draws': sum(c['goals_for'] == c['goals_against'] for c in cells),
                             'losses': sum(c['goals_for'] < c['goals_against'] for c in cells),
                             'learner_touch_ticks': sum(c.get('learner_touch_ticks', 0) for c in cells),
                             'team_touch_ticks': sum(c.get('team_touch_ticks', 0) for c in cells)}
        return {**totals, 'paired_goal_diff_per_minute': interval(list(values.values())),
                'paired_seed_means': values}

    per_format = {validate_format(*fmt): group([p for p in records if p['candidate']['format'] == validate_format(*fmt)])
                  for fmt in formats}
    overall = group(records)
    ci = overall['paired_goal_diff_per_minute']
    return {'overall': overall, 'per_format': per_format,
            'per_rival': {name: group([p for p in records if p['candidate']['rival'] == name]) for name in rivals},
            'selection_status': 'EXPLORATORY_POSITIVE' if ci['lower'] is not None and ci['lower'] > 0 else 'CLOSE_OR_INCONCLUSIVE',
            'confirmed': False, 'promoted': False, 'independent_seed_clusters': seeds,
            'note': 'Bootstrap intervals cluster colors, rivals and formats by seed. Short screens and '
                    'per-format comparisons are exploratory, not multiple-comparison-adjusted promotion '
                    'tests or evidence of SSL rank. Confirm promising models on fresh seeds and longer '
                    'offline matches. A team score can come from a frozen teammate.'}


def evaluate(candidate, reference, rivals, *, out, identity, formats=FORMATS, seeds=4,
             seconds=30., seed_base=730_000_000, scripted_student=False, pause_path=None):
    formats = parse_formats(formats)
    if not rivals or type(seeds) is not int or not 1 <= seeds <= 256:
        raise ValueError('Need frozen rivals and 1..256 independent seeds')
    if type(seed_base) is not int or seed_base < 0 or seed_base + 997 * (seeds - 1) >= 2 ** 63 - 100_000:
        raise ValueError('Evaluation seed range is invalid')
    if not math.isfinite(seconds) or not 0 < seconds <= 3600 or round(seconds * 120) < 1:
        raise ValueError('Match duration must be between one tick and 3600 seconds')
    verify_identity_files(identity)
    protocol = {'schema': SCHEMA, 'identity': identity, 'formats': [list(f) for f in formats],
                'rivals': list(rivals), 'seeds': seeds, 'seconds': float(seconds), 'seed_base': seed_base,
                'scripted_student': bool(scripted_student), 'frozen_scripted_kickoff': True,
                'learner_slots': 1,
                'teammate_policy': 'same_frozen_reference_for_candidate_and_reference',
                'candidate_weights': policy_digest(candidate), 'reference_weights': policy_digest(reference),
                'rival_weights': {name: policy_digest(actor) for name, actor in rivals.items()},
                'runtime': runtime_identity(), 'code': code_identity()}
    out = Path(out)
    with process_lock(out.with_name(out.name + '.lock')):
        state = read_json(out, {'protocol': protocol, 'records': [], 'done': False})
        if state['protocol'] != protocol:
            raise ValueError('Team evaluation inputs, runtime or code changed; use a fresh output filename')
        keys = validate_records(state['records'], formats=formats, rivals=rivals, seeds=seeds,
                                seed_base=seed_base, seconds=seconds, scripted_student=scripted_student,
                                complete=bool(state['done']))
        if state['done']:
            # Recompute the summary rather than trusting edited cached conclusions.
            state['summary'] = summarize(state['records'], formats=formats, rivals=rivals, seeds=seeds,
                                         seed_base=seed_base, seconds=seconds, scripted_student=scripted_student)
            return state
        atomic_json(out, state)
        total = len(expected_cells(formats, rivals, seeds, seed_base))
        started = time.perf_counter()
        new = 0
        print('TEAM_EVAL_BEGIN', 'completed_pairs', len(keys), 'total_pairs', total, flush=True)
        for j in range(seeds):
            seed = seed_base + 997 * j
            for fmt in formats:
                for rival in rivals:
                    for side in SIDES:
                        key = (validate_format(*fmt), rival, side, seed)
                        if key in keys:
                            continue
                        if pause_path and Path(pause_path).exists():
                            raise EvaluationPaused('Paused between complete paired team matches')
                        verify_identity_files(identity)
                        args = dict(rival=rival, side=side, seed=seed, seconds=seconds,
                                    our_size=fmt[0], their_size=fmt[1], scripted_student=scripted_student,
                                    teammate_actor=reference)
                        c = match(candidate, rivals, **args)
                        r = match(reference, rivals, **args)
                        verify_identity_files(identity)
                        state['records'].append({'candidate': c, 'reference': r})
                        keys.add(key)
                        new += 1
                        atomic_json(out, state)
                        eta = (time.perf_counter() - started) / new * (total - len(keys))
                        print('TEAM_EVAL', len(keys), '/', total, key[0], rival, side,
                              f"candidate {c['goals_for']}:{c['goals_against']} reference {r['goals_for']}:{r['goals_against']}",
                              'eta_minutes', round(eta / 60, 1), flush=True)
        state['summary'] = summarize(state['records'], formats=formats, rivals=rivals, seeds=seeds,
                                     seed_base=seed_base, seconds=seconds, scripted_student=scripted_student)
        verify_identity_files(identity)
        state['done'] = True
        atomic_json(out, state)
        return state


def audit(source=DEFAULT_SOURCE, *, out=None, seed=810_000_000):
    """Check every car and both colors in all nine formats, before/after controls."""
    from afk_team_research import encode_multi
    from vendor.nexto.nexto_obs import NextoObsBuilder
    source = Path(source).resolve()
    source_hash = sha256(source)
    actor = load_actor(ROOT, source)
    report = {'schema': SCHEMA, 'source': {'path': str(source), 'sha256': source_hash},
              'runtime': runtime_identity(), 'code': code_identity(), 'seed': seed, 'records': [],
              'logit_tolerance': {'absolute': 1e-5, 'relative': 1e-6, 'greedy_actions_must_match': True},
              'purpose': 'Observation and inference contract only; this is not a strength evaluation.'}
    if out is not None and Path(out).exists():
        raise FileExistsError(f'Preserve the existing audit: {out}')
    for ours, theirs in FORMATS:
        for side in SIDES:
            env = TeamEnv({'source': actor}, our_size=ours, their_size=theirs, fixed_side=side,
                          fixed_rival='source', teammate_actor=actor, task_name='match', max_seconds=1.)
            try:
                obs = env.reset(seed)
                for phase in ('reset', 'after_controls'):
                    if phase == 'after_controls':
                        env.step(greedy(actor, obs))
                    contract = env.observation_contract()
                    padded = env.observer.observe(env.state, env.previous)
                    encoded, ids = encode_multi(env.state)
                    unpadded_builder = NextoObsBuilder(n_players=len(ids), tick_skip=8)
                    raw = unpadded_builder.batched_build_obs(encoded[None])
                    for i, aid in enumerate(ids):
                        unpadded_builder.add_actions(raw, np.asarray(env.previous.get(aid, np.zeros(8))), i)
                        plain = tuple(part[0].astype(np.float32) for part in raw[i])
                        strict = padded[aid]
                        active = strict[2] == 0
                        with torch.inference_mode():
                            p = base.logits_of(actor, base.to_tensors(plain))
                            s = base.logits_of(actor, base.to_tensors(strict))
                        feature_error = float(np.max(np.abs(strict[1][active] - plain[1])))
                        query_error = float(np.max(np.abs(strict[0] - plain[0])))
                        logit_error = float((p - s).abs().max().item())
                        controls_match = bool(np.array_equal(strict[0][0, 24:], np.asarray(env.previous.get(aid, np.zeros(8)), dtype=np.float32)))
                        record = {'format': validate_format(ours, theirs), 'learner_side': side,
                                  'phase': phase, 'car': aid, 'contract': contract[aid],
                                  'active_feature_error': feature_error, 'query_error': query_error,
                                  'unpadded_logit_error': logit_error,
                                  'previous_controls_match': controls_match,
                                  'greedy_action_equal': bool(p.argmax(-1).item() == s.argmax(-1).item()),
                                  'logits_numerically_equal': bool(torch.allclose(p, s, atol=1e-5, rtol=1e-6)),
                                  'finite_policy': bool(torch.isfinite(p).all() and torch.isfinite(s).all())}
                        record['passed'] = bool(contract[aid]['passed'] and feature_error <= 1e-6 and query_error <= 1e-6
                                                and record['logits_numerically_equal'] and record['greedy_action_equal']
                                                and controls_match and record['finite_policy'])
                        report['records'].append(record)
            finally:
                env.close()
            print('TEAM_OBSERVATION_AUDIT', f'{ours}v{theirs}', side, 'passed',
                  all(r['passed'] for r in report['records'] if r['format'] == f'{ours}v{theirs}' and r['learner_side'] == side), flush=True)
    if sha256(source) != source_hash:
        raise RuntimeError('Audit source changed during the read-only audit')
    report['source_unchanged'] = True
    report['passed'] = bool(report['records']) and all(r['passed'] for r in report['records'])
    report['max_unpadded_logit_error'] = max(r['unpadded_logit_error'] for r in report['records'])
    if out is not None:
        atomic_json(out, report)
    return report


def path_identity(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256(path)}


def named_paths(values):
    result = {}
    for value in values:
        if '=' not in value:
            raise ValueError('Each --rival must be name=checkpoint_path')
        name, path = value.split('=', 1)
        if not name.strip() or name in result:
            raise ValueError('Rival names must be nonempty and unique')
        result[name] = Path(path).resolve()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    a = subs.add_parser('audit')
    a.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    a.add_argument('--out', type=Path)
    a.add_argument('--seed', type=int, default=810_000_000)
    e = subs.add_parser('evaluate')
    e.add_argument('--candidate', type=Path, required=True)
    e.add_argument('--reference', type=Path, default=DEFAULT_SOURCE)
    e.add_argument('--rival', action='append', default=[], help='Repeat name=checkpoint_path; defaults to original Nexto')
    e.add_argument('--seeds', type=int, default=4)
    e.add_argument('--seconds', type=float, default=30.)
    e.add_argument('--formats', default='all')
    e.add_argument('--seed-base', type=int, default=730_000_000)
    e.add_argument('--scripted-learner', action='store_true')
    e.add_argument('--out', type=Path, required=True)
    e.add_argument('--pause-path', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.command == 'audit':
        out = args.out or ROOT / 'data/isolated/team_observation_audits' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        result = audit(args.source, out=out, seed=args.seed)
        print('TEAM_AUDIT_REPORT', out.resolve(), 'passed', result['passed'], flush=True)
        if not result['passed']:
            raise SystemExit(2)
    else:
        paths = named_paths(args.rival) or {'nexto': ROOT / 'vendor/nexto/nexto-model.pt'}
        identity = {'candidate': path_identity(args.candidate), 'reference': path_identity(args.reference),
                    'rivals': {name: path_identity(path) for name, path in paths.items()}}
        candidate = load_actor(ROOT, args.candidate)
        reference = load_actor(ROOT, args.reference)
        rivals = {name: load_actor(ROOT, path) for name, path in paths.items()}
        result = evaluate(candidate, reference, rivals, out=args.out, identity=identity,
                          formats=parse_formats(args.formats), seeds=args.seeds, seconds=args.seconds,
                          seed_base=args.seed_base, scripted_student=args.scripted_learner, pause_path=args.pause_path)
        print('TEAM_EVALUATION_REPORT', args.out.resolve(), result['summary']['selection_status'], flush=True)


if __name__ == '__main__':
    main()
