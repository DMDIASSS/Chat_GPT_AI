"""READ-ONLY scenario diagnostics for the Chat_GPT_AI native Nexto models.

Every comparison uses fresh, paired seeds for blue/orange sides. Scenario types
are separated, unlike prior single aggregate first-goal tournament scores.
Never trains, promotes, or writes checkpoint files. Runs in RocketSim on your PC.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys
import time
import traceback

from rl_diagnostic_core import (
    KINDS, generate_plan, aggregate_pair_rows, paired_difference,
    kickoff_quality, aggregate_kickoff_quality,
    KICKOFF_SNAPSHOT_DECISIONS, KICKOFF_GOAL_DECISIONS,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
MAIN = DATA / 'autoleague'
REPORTS = DATA / 'scenario_diagnostics'
CYCLE_09 = (MAIN / 'backups' /
    '20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt')
WAVEDASH = DATA / 'mechanics' / 'wavedash' / 'last.pt'
EXPECTED_CYCLE_09 = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
EXPECTED_WAVEDASH = '57e330a7b4d3487fd304ec9e3252b847df3fea1e59c6351fc7cd4548156809b3'
FORMAT_VERSION = 2


def timestamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def selected_paths(extras: list[str]):
    sources = {'champion': MAIN / 'champion.pt', 'cycle09': CYCLE_09, 'wavedash': WAVEDASH}
    for spec in extras:
        if '=' not in spec:
            raise ValueError('--add-model must be NAME=PATH')
        label, name = spec.split('=', 1)
        if not label or not name or label in sources or not label.replace('_','').isalnum():
            raise ValueError('Unique alphanumeric name required for --add-model')
        sources[label] = Path(name)
    return sources


def initial_checks(paths, *, champion_state=True):
    from auto_league import sha256
    if champion_state and not (MAIN / 'league_state.json').is_file():
        raise FileNotFoundError('Main league_state.json not found; aborting for checkpoint safety')
    result = {}
    for name, path in paths.items():
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f'{name}: missing {path}')
        digest = sha256(path)
        if name == 'cycle09' and digest != EXPECTED_CYCLE_09:
            raise RuntimeError('Cycle 9 file differs from earlier tournament SHA; refusing to compare wrong weights')
        if name == 'wavedash' and digest != EXPECTED_WAVEDASH:
            raise RuntimeError('Wavedash file differs from earlier tournament SHA; refusing to compare wrong weights')
        result[name] = {'path': str(path), 'sha256': digest}
    if champion_state:
        state = json.loads((MAIN / 'league_state.json').read_text(encoding='utf-8'))
        if state.get('phase') != 'train' or state.get('champion_sha') != result['champion']['sha256']:
            raise RuntimeError('Main champion and league state do not match or promotion is in progress')
    return result


class DiagnosticMatch:
    """Wraps project Match without changing training or state-mutator source files.

    Uses the project's exact ChatGPTCurriculum for single scenario classes.
    """
    def __init__(self, teacher, engine, orange: bool, kind: str):
        from native_nexto import Match
        from chatgpt_ai.curriculum import ChatGPTCurriculum
        from chatgpt_ai.curriculum_config import DISTRIBUTIONS
        if kind not in KINDS:
            raise ValueError(kind)
        # Add one-off, deterministic scenario presets only to this process.
        # No file on disk is modified; category sampling is exactly 100%.
        if kind != 'kickoff':
            preset = '__diagnostic_' + kind
            DISTRIBUTIONS[preset] = ((kind, 1.0),)
            mutator = ChatGPTCurriculum(preset)
        else:
            mutator = None

        # Match() calls self.reset(); replace reset only for this instance before
        # constructing it, while retaining its genuine observe/step semantics.
        class OneScenarioMatch(Match):
            def reset(self):
                base = self.engine.create_base_state()
                self.team_mutator.apply(base, {})
                if mutator is not None:
                    mutator.apply(base, {})  # internally initializes kickoffs first
                else:
                    self.kickoff.apply(base, {})
                self.state = self.engine.set_state(base, {})
                self.previous = {}
                self.ours = next(agent for agent, car in self.state.cars.items()
                    if bool(car.is_orange) == self.our_orange)
                self.opponent = next(agent for agent in self.state.cars if agent != self.ours)
                self.decisions = 0
                self.contacts = {'ours': 0, 'nexto': 0}
                return self.observe()

        self.match = OneScenarioMatch(teacher, engine, training_side_orange=orange,
                                     scenarios=kind)


def kickoff_state_snapshot(match, boosts_gained):
    """Capture the 4-second physics state by value, so later steps cannot mutate it."""
    import numpy as np

    state = match.state
    ball = np.asarray(state.ball.position, dtype=float)
    ball_v = np.asarray(state.ball.linear_velocity, dtype=float)
    output = {'ball_x': float(ball[0])}
    for side, car_id in (('a', match.ours), ('b', match.opponent)):
        car = state.cars[car_id]
        pos = np.asarray(car.physics.position, dtype=float)
        toward_opponent = -1 if car.is_orange else 1
        output[side] = {
            'ball_distance': float(np.linalg.norm(pos - ball)),
            'boost_remaining': float(car.boost_amount),
            'boost_gained': float(boosts_gained[side]),
            'oriented_ball_y': toward_opponent * float(ball[1]),
            'oriented_ball_vy': toward_opponent * float(ball_v[1]),
        }
    return output


def simulate_pair(actor_a, actor_b, teacher, engine, *, kind, seed, decisions):
    import numpy as np
    from auto_league import action_greedy, initial_fingerprint
    sides = []
    for orange in (False, True):
        random.seed(seed)
        np.random.seed(seed % (2**32))
        match = DiagnosticMatch(teacher, engine, orange, kind).match
        fingerprint = initial_fingerprint(match)
        result = 'draw'
        early_goal = None
        snapshot = None
        boost_gained = {'a': 0.0, 'b': 0.0}
        for _ in range(decisions):
            if kind == 'kickoff' and match.decisions < KICKOFF_SNAPSHOT_DECISIONS:
                old_boost_a = float(match.state.cars[match.ours].boost_amount)
                old_boost_b = float(match.state.cars[match.opponent].boost_amount)
            own, opp = match.observe()
            a = action_greedy(actor_a, own)
            b = action_greedy(actor_b, opp)
            _, done, result = match.step(a, b, decisions)
            if kind == 'kickoff':
                if match.decisions <= KICKOFF_SNAPSHOT_DECISIONS:
                    boost_gained['a'] += max(0.0, float(match.state.cars[match.ours].boost_amount) - old_boost_a)
                    boost_gained['b'] += max(0.0, float(match.state.cars[match.opponent].boost_amount) - old_boost_b)
                if match.decisions == min(KICKOFF_SNAPSHOT_DECISIONS, decisions):
                    snapshot = kickoff_state_snapshot(match, boost_gained)
                if done and result != 'draw' and match.decisions <= KICKOFF_GOAL_DECISIONS:
                    early_goal = result
            if done:
                break
        if kind == 'kickoff' and snapshot is None and early_goal is None:
            snapshot = kickoff_state_snapshot(match, boost_gained)
        side_row = {'orange': orange, 'outcome': result, 'fingerprint': fingerprint,
                    'decisions': match.decisions,
                    'touches_a': match.contacts['ours'],
                    'touches_b': match.contacts['nexto']}
        if kind == 'kickoff':
            side_row['kickoff_quality'] = kickoff_quality(snapshot, early_goal)
        sides.append(side_row)
    return {'scenario': kind, 'seed': seed, 'sides': sides}


def cache_key(a_hash, b_hash, kind, seed, decisions):
    return json.dumps([FORMAT_VERSION, a_hash,b_hash,kind,seed,decisions], separators=(',', ':'))


def read_cache(path):
    result = {}
    if not path.exists():
        return result
    with path.open(encoding='utf-8') as reader:
        for line in reader:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a process was killed during a cache append
            if entry.get('key') and entry.get('row'):
                result[entry['key']] = entry['row']
    return result


def store_cache(path, key, row):
    # A hard kill can leave a partial last JSONL line; separate it first.
    if path.exists() and path.stat().st_size:
        with path.open('rb') as reader:
            reader.seek(-1, 2)
            trailing_newline = reader.read(1) == b'\n'
    else:
        trailing_newline = True
    with path.open('a', encoding='utf-8') as writer:
        if not trailing_newline:
            writer.write('\n')
        writer.write(json.dumps({'key': key, 'row': row}, separators=(',',':')) + '\n')
        writer.flush()
        os.fsync(writer.fileno())


def run(args):
    from auto_league import actor_from, sha256, exclusive_league_lock
    from nexto_teacher import NextoTeacher
    from rlgym.rocket_league.sim import RocketSimEngine
    import torch

    REPORTS.mkdir(parents=True, exist_ok=True)
    with exclusive_league_lock(MAIN):
        manifest = initial_checks(selected_paths(args.add_model))
        print('Models:', ', '.join(manifest), flush=True)
        for name, metadata in manifest.items():
            print(f' {name} {metadata["sha256"][:12]} {metadata["path"]}', flush=True)
        # Ensure source actor architecture is compatible before any simulation.
        actors = {name: actor_from(Path(info['path']), 'cpu') for name, info in manifest.items()}
        teacher = NextoTeacher('cpu')
        actors['original_nexto'] = teacher.actor
        torch.set_num_threads(2)
        cache_path = REPORTS / 'paired_runs_cache_v2.jsonl'
        cache = read_cache(cache_path)
        kinds = ('kickoff',) if args.kickoff_only else KINDS
        pairs_plan = generate_plan(args.seed, args.pairs)
        control_plan = generate_plan(args.seed+191919, min(args.pairs, args.control_pairs))
        jobs = [(n,'original_nexto', pairs_plan) for n in manifest]
        if not args.no_head_to_head:
            names = list(manifest)
            jobs.extend((a,b,pairs_plan) for i,a in enumerate(names) for b in names[i+1:])
        jobs.append(('original_nexto','original_nexto',control_plan))
        all_rows = {}
        used_from_cache = 0
        simulated = 0
        engine = RocketSimEngine(rlbot_delay=False)
        try:
            for name_a, name_b, plan in jobs:
                pair_rows = []
                print(f'=== {name_a} VS {name_b} ===', flush=True)
                for kind in kinds:
                    rows_kind = []
                    for seed in plan[kind]:
                        key = cache_key(manifest.get(name_a, {}).get('sha256','original'),
                                        manifest.get(name_b, {}).get('sha256','original'),
                                        kind,seed,args.decisions)
                        if key in cache:
                            row = cache[key]
                            used_from_cache += 1
                        else:
                            row = simulate_pair(actors[name_a],actors[name_b],teacher,engine,
                                                kind=kind,seed=seed,decisions=args.decisions)
                            store_cache(cache_path,key,row)
                            cache[key] = row
                            simulated += 1
                        rows_kind.append(row)
                        pair_rows.append(row)
                    details = aggregate_pair_rows(rows_kind,ci_seed=args.seed + len(pair_rows))
                    if kind == 'kickoff':
                        kq = aggregate_kickoff_quality(rows_kind, ci_seed=args.seed+len(pair_rows)+1)
                        print(f'   KICKOFF quality={kq["kickoff_quality_score"]:.1%} '
                              f'control/boost success A={kq["model_a_quality_success_rate"]:.1%} '
                              f'B={kq["model_b_quality_success_rate"]:.1%} '
                              f'cases={kq["exclusive_outcomes"]}', flush=True)
                    warn = f' [start mismatches={details["paired_initial_state_mismatches"]}]' if details['paired_initial_state_mismatches'] else ''
                    print(f' {kind:<8} {details["score"]:.1%} W={details["outcomes"]["ours"]} '
                          f'L={details["outcomes"]["nexto"]} D={details["outcomes"]["draw"]}{warn}', flush=True)
                all_rows[f'{name_a}__vs__{name_b}'] = pair_rows
                overall = aggregate_pair_rows(pair_rows,ci_seed=args.seed)
                print(f' TOTAL {overall["score"]:.1%} CI {overall["bootstrap_95_percent_interval"]}', flush=True)
        finally:
            engine.close()
        # Refuse report if someone replaced a model during the evaluation.
        changed = [name for name, info in manifest.items()
                   if sha256(Path(info['path'])) != info['sha256']]
        if changed:
            raise RuntimeError('Checkpoint content changed DURING benchmark: ' + ', '.join(changed))
        # Build category reports and matched-pair differences.
        report = {'kind': 'scenario_diagnostics_v2', 'created_utc': timestamp(),
                  'format_version': FORMAT_VERSION,
                  'kickoff_quality_protocol': (
                    'Goal within 6 seconds overrides; otherwise at 4 seconds '
                    'ball within 1400uu and 150uu closer than opponent OR boost pickup >=10 '
                    'and remaining >=30 when not in own-goal danger. Both may satisfy = contested. '
                    'Kickoff-quality separate from first-goal outcomes.'),
                  'protocol': '1v1 first-goal or decision cap; greedy policies; blue+orange per paired seed',
                  'caveats': ['NOT full five-minute matches',
                    'Ground/defense/aerial/wall states are synthetic training-curriculum distributions, not human replay states',
                    'Bootstrap confidence intervals do NOT correct for model selection from a prior tournament',
                    'No checkpoint promotion; all models remain intact'],
                  'decision_cap': args.decisions, 'seed':args.seed,
                  'pairs_per_category':args.pairs, 'models':manifest,
                  'results':{}, 'paired_differences_vs_champion':{},
                  'cache_stats':{'reused_pairs':used_from_cache,'new_pairs':simulated}}
        for match, rows in all_rows.items():
            report['results'][match] = {
                'overall': aggregate_pair_rows(rows,ci_seed=args.seed + 271),
                'by_scenario':{kind:aggregate_pair_rows([r for r in rows if r['scenario']==kind],
                                                 ci_seed=args.seed+ix*101)
                         for ix,kind in enumerate(kinds)},
                'kickoff_quality': aggregate_kickoff_quality([r for r in rows if r['scenario']=='kickoff'],
                                  ci_seed=args.seed+71) if any(r['scenario']=='kickoff' for r in rows) else None}
        benchmark = all_rows['champion__vs__original_nexto']
        for n in manifest:
            if n == 'champion':
                continue
            report['paired_differences_vs_champion'][n] = paired_difference(
                all_rows[f'{n}__vs__original_nexto'],benchmark,
                seed=args.seed+37)
        mismatches = sum(
            item['overall']['paired_initial_state_mismatches']
            for item in report['results'].values())
        report['paired_start_integrity'] = {'mismatching_pairs': mismatches,
             'valid': mismatches == 0,
             'warning': 'If any mismatches, rerun after investigating simulator reset determinism.'}
        if mismatches:
            print(f'WARNING: {mismatches} paired starts are not identical across sides. '
                  'Do not draw conclusions until simulator reset is fixed.',flush=True)
        report['ranked_vs_original_nexto'] = sorted(manifest,
            key=lambda n: report['results'][f'{n}__vs__original_nexto']['overall']['score'],
            reverse=True)
        report['scenario_leaders'] = {
            kind: sorted(manifest,
                key=lambda n: report['results'][f'{n}__vs__original_nexto']['by_scenario'][kind]['score'],
                reverse=True)
            for kind in kinds
        }
        print('\n=== RANKING VS ORIGINAL NEXTO (FIRST GOAL ONLY) ===', flush=True)
        for rank, name in enumerate(report['ranked_vs_original_nexto'], 1):
            stat=report['results'][f'{name}__vs__original_nexto']['overall']
            low, high=stat['bootstrap_95_percent_interval']
            print(f'{rank}. {name:<12} {stat["score"]:.1%} (exploratory 95% CI {low:.1%}..{high:.1%})',flush=True)
        print('Do not promote models based on this test alone.', flush=True)
        from auto_league import atomic_json
        out = REPORTS / f'scenario_diagnostics_v2_{timestamp()}_seed{args.seed}_n{args.pairs}.json'
        atomic_json(out, report)
        print(f'\nCOMPLETE: {out}', flush=True)
        print('Compare scenario scores and paired difference intervals before proposing reward changes.', flush=True)
        return 0


def parse(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pairs',type=int,default=8,help='paired seeds per scenario for each matchup')
    p.add_argument('--decisions',type=int,default=750,help='15Hz decisions per first-goal episode; 750 = 50 seconds')
    p.add_argument('--seed',type=int,default=50778123,help='held-out eval seed, separate from prior tournament')
    p.add_argument('--control-pairs',type=int,default=3)
    p.add_argument('--add-model',action='append',default=[],metavar='NAME=PATH',help='include an isolated trained checkpoint')
    p.add_argument('--no-head-to-head',action='store_true')
    p.add_argument('--kickoff-only',action='store_true',
                   help='only kickoff scenarios; use --decisions 90 for 6-second verdicts')
    p.add_argument('--check',action='store_true',help='validate model names and hashes without simulating')
    p.add_argument('--smoke',action='store_true',help='one pair/category and short episodes for a simulator check')
    args=p.parse_args(argv)
    if args.smoke:
        args.pairs=1
        args.control_pairs=1
        args.decisions=90
    if args.kickoff_only and args.decisions < KICKOFF_SNAPSHOT_DECISIONS:
        p.error('--kickoff-only requires --decisions >=60 for a complete kickoff snapshot')
    if args.pairs < 1 or args.decisions < 1 or args.control_pairs < 1:
        p.error('pairs, decisions, and control-pairs must be >= 1')
    return args


def main(argv=None):
    args = parse(argv)
    if args.check:
        from auto_league import exclusive_league_lock
        with exclusive_league_lock(MAIN):
            for name, info in initial_checks(selected_paths(args.add_model)).items():
                print('OK',name,info['sha256'][:16],info['path'])
        print('PREFLIGHT OK. No simulator started and no model changed.')
        return 0
    return run(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Stopped. Completed paired episodes are cached for resume.',file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}: {exc}',file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
