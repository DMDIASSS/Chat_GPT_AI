"""Slater v0.3.9 throughput preflight: safe, read-only simulator benchmark.

Does not train, save weights, or export RLBot bots. Measures single-process
inference+physics rollout throughput with protected u60, Nexto, and Cycle9.
The measured rate EXCLUDES PPO backpropagation and validation overhead.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import time
from datetime import datetime, timezone

ACTION_REPEAT = 8
TICKS_PER_SECOND = 120
DECISIONS_PER_SIM_HOUR = (TICKS_PER_SECOND / ACTION_REPEAT) * 3600
BUDGETS = (1_000_000, 10_000_000, 100_000_000, 1_000_000_000)
MODES = ('old_greedy', 'old_script', 'old_stock', 'tick_greedy', 'tick_script', 'tick_stock')


def estimates(decisions_per_second: float) -> list[dict]:
    """Only raw rollout estimates. PPO, evaluation, I/O and workers add costs."""
    if not math.isfinite(decisions_per_second) or decisions_per_second <= 0:
        raise ValueError('Rate must be positive and finite')
    return [
        {'decisions': n,
         'simulated_agent_hours': round(n / DECISIONS_PER_SIM_HOUR, 2),
         'wallclock_hours_at_measured_rollout_rate': round(n / decisions_per_second / 3600, 2)}
        for n in BUDGETS
    ]


def safe_output(root: Path, value: str) -> Path:
    if not value:
        raise ValueError('Missing output path')
    p = (root / value).resolve()
    permitted = (root / 'data' / 'isolated').resolve()
    if not p.is_relative_to(permitted) or p.suffix != '.json':
        raise ValueError('Report must be a .json file under data/isolated')
    if p.exists() or p.with_name(p.name + '.partial').exists():
        raise FileExistsError(f'Output already exists; select a new filename: {p}')
    return p


def validate_options(decisions: int, warmup: int, max_steps: int, modes: tuple[str, ...]) -> None:
    if not (32 <= decisions <= 100_000):
        raise ValueError('decisions must be 32..100000 per configuration')
    if not (0 <= warmup <= 256):
        raise ValueError('warmup must be 0..256')
    if not (180 <= max_steps <= 4500):
        raise ValueError('max-episode-steps must be 180..4500')
    if not modes or len(modes) != len(set(modes)) or any(m not in MODES for m in modes):
        raise ValueError('Invalid, empty, or duplicate mode')


def measure(mode, actor, original, nexto, actions, *, decisions, warmup,
            max_episode_steps, seed, side='blue') -> dict:
    import numpy as np
    import torch
    from afk_team_research import TeamObserver
    import slater_cycle9_native_ppo_v025 as base
    import slater_nexto_kickoff_v037a as old
    from slater_nexto_tick_eval_v038b import TickNextoEnv

    torch.manual_seed(seed)
    np.random.seed(seed % (2**32 - 1))
    random.seed(seed)
    observer = TeamObserver()
    if mode.startswith('old_'):
        old_name = {'old_greedy':'nexto_greedy', 'old_script':'nexto_script',
                    'old_stock':'nexto_stock_approx'}[mode]
        env = old.ScriptedNextoEnv(actions, observer, (original, nexto),
                                   max_steps=max_episode_steps, device='cpu',
                                   modes=(old_name,), fixed_side=side)
    else:
        name = {'tick_greedy':'nexto_greedy_tick',
                'tick_script':'nexto_script_tick', 'tick_stock':'nexto_stock_tick'}[mode]
        env = TickNextoEnv(actions, observer, (original, nexto), max_steps=max_episode_steps,
                           device='cpu', mode=name, fixed_side=side)
    episode = 0
    terminations = {'goals_for': 0, 'goals_against': 0, 'timeouts': 0}
    scripted_ticks = 0
    try:
        obs = env.reset(seed)
        # Warmup is excluded; restart the game and RNG before measurement.
        for i in range(warmup):
            with torch.inference_mode():
                a = int(base.logits_of(actor, base.to_tensors(obs)).argmax(-1).item())
            obs, _, done, _ = env.step(a)
            if done:
                episode += 1
                obs = env.reset(seed + episode)
        episode = 0
        torch.manual_seed(seed)
        np.random.seed(seed % (2**32 - 1))
        random.seed(seed)
        obs = env.reset(seed)
        start = time.perf_counter()
        for _ in range(decisions):
            with torch.inference_mode():
                a = int(base.logits_of(actor, base.to_tensors(obs)).argmax(-1).item())
            obs, _, done, info = env.step(a)
            if done:
                outcome = int(info['outcome'])
                if outcome == 1: terminations['goals_for'] += 1
                elif outcome == -1: terminations['goals_against'] += 1
                else: terminations['timeouts'] += 1
                scripted_ticks += int(info.get('script_physics_ticks') or
                                      (info.get('script_action_steps', 0)*ACTION_REPEAT))
                episode += 1
                obs = env.reset(seed + episode)
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            raise RuntimeError('Nonpositive elapsed time')
        rate = decisions / elapsed
        return {
            'mode': mode, 'side': side,
            'decisions': decisions,
            'elapsed_seconds': round(elapsed, 4),
            'decisions_per_second': round(rate, 3),
            'nominal_physics_ticks_per_second': round(rate*ACTION_REPEAT, 3),
            'equivalent_single_agent_realtime_multiplier': round(rate/(TICKS_PER_SECOND/ACTION_REPEAT),3),
            'finished_episodes': sum(terminations.values()),
            'outcomes': terminations,
            'scripted_ticks_in_finished_episodes_only': scripted_ticks,
            'budget_estimates': estimates(rate),
        }
    finally:
        env.close()


def run(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', default='data/isolated/slater_v027_campaign01_u0060.pt')
    parser.add_argument('--modes', default='old_script,tick_stock',
                        help='Comma-separated: ' + ','.join(MODES))
    parser.add_argument('--decisions', type=int, default=256,
                        help='Measured decisions PER opponent configuration')
    parser.add_argument('--warmup', type=int, default=16)
    parser.add_argument('--max-episode-steps', type=int, default=600)
    parser.add_argument('--seed', type=int, default=20261011)
    parser.add_argument('--side', choices=('blue', 'orange'), default='blue')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    modes = tuple(x.strip() for x in args.modes.split(','))
    validate_options(args.decisions, args.warmup, args.max_episode_steps, modes)
    if not (1 <= args.seed < 2**31 - 100_000):
        parser.error('Invalid seed')
    root = Path.cwd().resolve()
    target = safe_output(root, args.out)

    import torch
    import slater_nexto_kickoff_v037a as old
    import slater_cycle9_native_ppo_v025 as base
    torch.set_num_threads(2)
    checkpoint = (root / args.checkpoint).resolve()
    actor, original, nexto, actions, _, provenance = old.load_protected(root, checkpoint)
    original_hash = base.sha256(checkpoint)
    results = []
    for mode in modes:
        entry = measure(mode, actor, original, nexto, actions,
                        decisions=args.decisions, warmup=args.warmup,
                        max_episode_steps=args.max_episode_steps,
                        seed=args.seed, side=args.side)
        results.append(entry)
        print('V039_THROUGHPUT', json.dumps(entry, sort_keys=True), flush=True)
    if base.sha256(checkpoint) != original_hash:
        raise RuntimeError('Protected source checkpoint modified during benchmark')
    report = {
        'version': 'v0.3.9-preflight',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'SINGLE_PROCESS_ROLLOUT_MEASURED_NOT_FULL_PPO',
        'provenance': provenance,
        'checkpoint': str(checkpoint),
        'config': {'modes': list(modes), 'decisions_per_mode': args.decisions,
                   'warmup_per_mode': args.warmup, 'max_episode_steps': args.max_episode_steps,
                   'seed': args.seed, 'side': args.side},
        'measurements': results,
        'cautions': [
            'Collected action decisions, not PPO optimizer steps and not video frames.',
            'Single-process CPU inference + RocketSim only; PPO backprop and evaluation are excluded.',
            'Simulated gameplay hours are agent-hours for one 120Hz game with action-repeat=8.',
            'Tick-aware Nexto uses a proxy kickoff pause, not a verified RocketSim-RLBot physics match.',
            'Measured rates vary by hardware, CPU thread settings, opponent, and episode length.',
            'No checkpoints are written, updated, promoted, or trained.',
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print('V039_REPORT', target)


if __name__ == '__main__':
    run()
