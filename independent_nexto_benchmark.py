"""Independent, read-only 1v1 first-goal benchmark for an AutoLeague champion.

This program does not train, promote, or alter any model or AutoLeague state.
Only creates a JSON report under benchmark_reports/ unless --no-save is passed.
Run on the original Windows installation with its existing .venv and RocketSim.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

from auto_league import DATA, ROOT, actor_from, duel, sha256, strict_json_dumps
from nexto_teacher import NextoTeacher


def build_cases(seed: int, pairs: int):
    """Fresh random seeds; evaluate BOTH teams from the same seed and scenario."""
    rng = random.Random(seed)
    cases = []
    for i in range(pairs):
        episode_seed = rng.randrange(1, 2**31)
        scenario = 'kickoff' if i % 4 == 0 else 'grounded'
        cases.append((episode_seed, False, scenario))
        cases.append((episode_seed, True, scenario))
    return cases


def read_champion_state(data_dir: Path):
    """Ensure we evaluate the SHA-verified, accepted champion, never candidate."""
    path = data_dir / 'champion.pt'
    state_path = data_dir / 'league_state.json'
    if not path.is_file() or not state_path.is_file():
        raise FileNotFoundError('Expected champion.pt and league_state.json in ' + str(data_dir))
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if state.get('phase') != 'train':
        raise RuntimeError('Promotion appears incomplete; do not benchmark until repaired.')
    actual_sha = sha256(path)
    if actual_sha != state.get('champion_sha'):
        raise RuntimeError('Champion SHA does not match league_state.json. No files were modified.')
    return path, state, actual_sha


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=DATA)
    parser.add_argument('--pairs', type=int, default=100,
                        help='Two games per pair (one blue, one orange). Default=100 pairs = 200 games.')
    parser.add_argument('--baseline-pairs', type=int, default=20,
                        help='Original Nexto vs itself sanity check, also both sides. Set 0 to skip.')
    parser.add_argument('--decisions', type=int, default=750,
                        help='Max decisions per first-goal episode (750 ≈ 50 seconds simulated time).')
    parser.add_argument('--seed', type=int, default=74192017,
                        help='Independent evaluation RNG seed; not one of the AutoLeague seeds.')
    parser.add_argument('--no-save', action='store_true',
                        help='Print report without writing a JSON report.')
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.pairs <= 0 or args.baseline_pairs < 0 or args.decisions <= 0:
        raise ValueError('pairs and decisions must be positive; baseline-pairs cannot be negative')
    data_dir = args.data_dir.resolve()
    champion_path, state, before_sha = read_champion_state(data_dir)
    print(f'READ-ONLY champion: {champion_path}', flush=True)
    print(f'Champion SHA256: {before_sha}', flush=True)
    print(f'Champion promotions: {state.get("promotions", "unknown")}; starting benchmark.', flush=True)
    torch.set_num_threads(2)
    teacher = NextoTeacher('cpu')
    champion = actor_from(champion_path, 'cpu')
    nexto = teacher.actor

    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=False)
    try:
        result = duel(champion, nexto, teacher, engine,
                      build_cases(args.seed, args.pairs), args.decisions,
                      label='HELD-OUT champion vs original Nexto')
        baseline = None
        if args.baseline_pairs:
            baseline = duel(nexto, nexto, teacher, engine,
                            build_cases(args.seed + 1000003, args.baseline_pairs), args.decisions,
                            label='CONTROL original Nexto vs itself')
    finally:
        engine.close()

    # The accepted champion must still be unchanged after this benchmark.
    after_sha = sha256(champion_path)
    if after_sha != before_sha:
        raise RuntimeError('Champion changed during benchmark! Report will NOT be saved. Stop other trainer processes and retry.')

    report = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'kind': 'independent_champion_nexto_first_goal',
        'evaluation_note': 'NOT a five-minute game; first goal or decision cap. '
                           'Seeds and sides paired; outcomes are not proof of general-game superiority.',
        'champion_sha256': before_sha,
        'champion_origin': state.get('champion_origin'),
        'league_cycle_at_start': state.get('cycle'),
        'opponent': 'unmodified original Nexto (teacher.actor)',
        'pair_count': args.pairs,
        'episode_count': 2 * args.pairs,
        'baseline_pair_count': args.baseline_pairs,
        'seed': args.seed,
        'max_decisions': args.decisions,
        'champion_vs_nexto': result,
        'original_nexto_vs_itself_control': baseline,
    }
    print('\n' + strict_json_dumps(report, indent=2), flush=True)
    if not args.no_save:
        directory = ROOT / 'benchmark_reports'
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = directory / f'heldout_nexto_{timestamp}.json'
        output.write_text(strict_json_dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'REPORT SAVED: {output}', flush=True)
    print('CHAMPION WAS NOT CHANGED.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Stopped by user. No model weights or AutoLeague files changed.', file=sys.stderr)
        sys.exit(130)
