"""Small grid calibration before doing any expensive CEM or policy training.

Never modifies / loads Nexto weights; archives results separate from v1.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from sf2_core import SoloSimulator, Script, rollout, metrics_json

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'data' / 'skillforge_v2' / 'calibration.json'


def search(args, simulator_factory=SoloSimulator):
    if args.train_seeds < 1 or args.test_seeds < 1:
        raise ValueError('Seed counts must be positive')
    if args.out.exists() and not args.overwrite:
        raise FileExistsError(f'{args.out} exists. Pass --overwrite only if desired.')
    thresholds = (27., 32., 38., 45., 53., 65., 80.)
    tilts = (0., 0.12, 0.22, 0.32)
    cancel_ticks = (4, 12, 20)
    train = list(range(args.seed, args.seed + args.train_seeds))
    test = list(range(args.seed + 10001, args.seed + 10001 + args.test_seeds))
    sim = simulator_factory()
    results = []
    best = None
    best_score = -float('inf')
    try:
        candidates = list(itertools.product(thresholds, tilts, cancel_ticks))
        print(f'Calibration: {len(candidates)} scripted combinations × {len(train)} training spawns', flush=True)
        for idx, (th, nose, cancel) in enumerate(candidates, 1):
            script = Script(threshold=th, nose=nose, cancel_ticks=cancel)
            data = [rollout(sim, seed, script, max_ticks=args.max_ticks) for seed in train]
            successes = sum(int(m.success) for m in data)
            mean_fitness = sum(m.fitness for m in data) / len(data)
            mean_gain = sum(m.final_speed - m.initial_speed for m in data) / len(data)
            # Binary success dominates shaping; shaping only breaks ties.
            score = successes * 20 + mean_fitness
            results.append({'script': vars(script), 'successes': successes,
                            'training_total': len(train), 'fitness': round(mean_fitness, 4),
                            'mean_speed_gain': round(mean_gain, 2)})
            if score > best_score:
                best_score = score
                best = script
                print(f'Best {idx}/{len(candidates)} success={successes}/{len(train)} '
                      f'fitness={mean_fitness:.2f} gain={mean_gain:+.0f} '
                      f'threshold={th:g} nose={nose:.2f} cancel={cancel}', flush=True)
        assert best is not None
        test_data = [rollout(sim, seed, best, max_ticks=args.max_ticks) for seed in test]
        passed = sum(int(m.success) for m in test_data)
        result = {'format': 'sf2-visual-calibration', 'training_seeds': train,
                  'holdout_seeds': test, 'candidate': vars(best),
                  'holdout_passed': passed, 'holdout_total': len(test),
                  'verified_for_imitation': False, # Separate physical verification required
                  'holdout': [metrics_json(x) for x in test_data],
                  'all_training_results': results}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix('.json.partial')
        tmp.write_text(json.dumps(result, indent=2), encoding='utf8')
        tmp.replace(args.out)
        print(f'Holdout: {passed}/{len(test)} provisional physics checks passed', flush=True)
        print('This does NOT train an AI. It saves controller scripts to visually inspect.', flush=True)
        print('Saved:', args.out, flush=True)
        return result
    finally:
        sim.close()


def parse(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--seed', type=int, default=700)
    p.add_argument('--train-seeds', type=int, default=4)
    p.add_argument('--test-seeds', type=int, default=16)
    p.add_argument('--max-ticks', type=int, default=115)
    p.add_argument('--out', type=Path, default=DEFAULT)
    p.add_argument('--overwrite', action='store_true')
    return p.parse_args(argv)


if __name__ == '__main__':
    try:
        search(parse())
    except (RuntimeError, ValueError, FileExistsError) as ex:
        print('ERROR:', ex)
        raise SystemExit(1)
