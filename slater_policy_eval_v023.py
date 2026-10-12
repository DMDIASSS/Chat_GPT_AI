"""Slater v0.2.3: READ-ONLY evaluation of isolated v0.2.2 shooting PPO.

Compare trained checkpoint against a seed-reconstructed untrained policy and
simple driving baselines using identical, newly sampled environment resets.
No training; no change to Cycle 9, the candidate checkpoint, or replay files.

Run at project root:
  .venv\\Scripts\\python.exe slater_policy_eval_v023.py \\
    --checkpoint data/isolated/native_ppo_v022_facingfix_01.pt \\
    --episodes 128 --out data/isolated/eval_v023_facingfix_01.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import torch

from slater_native_ppo_smoke_v022 import (
    ACTION_NAMES, ActorCritic, SoloShootingEnv, make_observation,
)

MODES = ('untrained_sampled', 'trained_sampled', 'untrained_greedy',
         'trained_greedy', 'drive_forward', 'boost_forward')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def allowed_output(out: Path) -> Path:
    root = (Path.cwd() / 'data' / 'isolated').resolve()
    p = out.resolve()
    if not p.is_relative_to(root) or p.suffix != '.json':
        raise ValueError(f'JSON output must be inside {root}')
    if p.exists():
        raise FileExistsError(f'Refusing to overwrite {p}')
    return p


def checkpoint_models(checkpoint: Path):
    # weights_only=True disallows arbitrary code execution from pickles.
    payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if not {'model', 'meta'}.issubset(payload):
        raise ValueError('Invalid isolated checkpoint format')
    meta = payload['meta']
    if meta.get('kind') != 'scratch_solo_shooting_ppo_smoke_headingfix_v022':
        raise ValueError(f'Expected v0.2.2 isolated checkpoint, got {meta.get("kind")}')
    seed = int(meta['seed'])
    torch.manual_seed(seed)
    untrained = ActorCritic().eval()  # Same seeded init as v022 main()
    trained = ActorCritic().eval()
    trained.load_state_dict(payload['model'], strict=True)
    reconstructed_delta = float(math.sqrt(sum(
        (p.detach() - q.detach()).square().sum().item()
        for p, q in zip(trained.parameters(), untrained.parameters())
    )))
    expected = float(meta['param_delta_l2'])
    if not np.isclose(reconstructed_delta, expected, rtol=1.e-5, atol=1.e-5):
        raise ValueError(f'Seed reconstruction mismatch: got {reconstructed_delta}, expected {expected}')
    return untrained, trained, meta, reconstructed_delta


@torch.no_grad()
def choose_action(mode, observation, untrained, trained, rng):
    if mode == 'drive_forward':
        return ACTION_NAMES.index('forward')
    if mode == 'boost_forward':
        return ACTION_NAMES.index('boost_forward')
    net = untrained if mode.startswith('untrained') else trained
    logits, _ = net(torch.as_tensor(observation, dtype=torch.float32).unsqueeze(0))
    if mode.endswith('_greedy'):
        return int(torch.argmax(logits, dim=-1).item())
    # Uses independent NumPy randomness to decouple action sampling from torch global RNG.
    probs = torch.softmax(logits[0], dim=-1).numpy().astype(np.float64)
    probs /= probs.sum()
    return int(rng.choice(len(probs), p=probs))


def evaluate_mode(mode: str, episodes: int, base_seed: int, max_steps: int,
                  untrained, trained):
    # Separate simulator RNG state per mode, but same reset seed and same number of
    # reset() calls, so scenario distribution and exact scenario sequence are paired.
    env = SoloShootingEnv(seed=base_seed, max_steps=max_steps)
    result = []
    try:
        for episode in range(episodes):
            obs = env.reset()
            # Independent per-episode action draws, not entangled with spawn RNG.
            rng = np.random.default_rng(base_seed + 10000000 + episode)
            while True:
                action = choose_action(mode, obs, untrained, trained, rng)
                obs, _, done, info = env.step(action)
                if done:
                    result.append({
                        'goal': int(bool(info['scored'])),
                        'touch': int(info['touches'] > 0),
                        'touches': int(info['touches']),
                        'return': float(info['total_reward']),
                        'final_ball_y': float(info['ball_y']),
                        'steps': int(info['steps']),
                    })
                    break
    finally:
        env.close()
    return result


def describe(rows):
    return {
        'episodes': len(rows),
        'goal_rate': float(np.mean([r['goal'] for r in rows])),
        'touch_rate': float(np.mean([r['touch'] for r in rows])),
        'avg_touches': float(np.mean([r['touches'] for r in rows])),
        'avg_return': float(np.mean([r['return'] for r in rows])),
        'avg_final_ball_y': float(np.mean([r['final_ball_y'] for r in rows])),
        'avg_steps': float(np.mean([r['steps'] for r in rows])),
    }


def paired_differences(a, b, seed=12345, resamples=3000):
    """Bootstrap paired trained-minus-baseline deltas, on same exact resets."""
    if len(a) != len(b):
        raise ValueError('Unpaired sample lengths')
    n = len(a)
    rng = np.random.default_rng(seed)
    result = {}
    for field in ('goal', 'touch', 'return'):
        x = np.asarray([z[field] for z in a], dtype=np.float64)
        y = np.asarray([z[field] for z in b], dtype=np.float64)
        d = x - y
        # Resample paired *scenario indices*. CI is descriptive, not a p-value.
        idx = rng.integers(0, n, size=(resamples, n))
        samples = d[idx].mean(axis=1)
        result[field] = {
            'delta': float(d.mean()),
            'bootstrap_95ci': [float(z) for z in np.percentile(samples, [2.5, 97.5])],
        }
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--episodes', type=int, default=128)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    if not (16 <= args.episodes <= 4096):
        ap.error('--episodes must be between 16 and 4096')
    ckpt = Path(args.checkpoint).resolve()
    if not ckpt.is_file():
        ap.error(f'Checkpoint not found: {ckpt}')
    expected_dir = (Path.cwd() / 'data' / 'isolated').resolve()
    if not ckpt.is_relative_to(expected_dir):
        ap.error(f'Only reads checkpoint from {expected_dir}')
    out = allowed_output(Path(args.out))
    torch.set_num_threads(2)
    before_hash = sha256(ckpt)
    untrained, trained, meta, delta = checkpoint_models(ckpt)
    seed = int(meta['seed'])
    max_steps = int(meta['args'].get('max_episode_steps', 120))
    # Completely held-out from seed, seed+100k pre/post, and seed+200k random.
    eval_seed = seed + 400000
    print('EVAL_ONLY: v0.2.2 checkpoint, no optimizer / PPO / replay / Cycle 9', flush=True)
    print('CHECKPOINT_SHA256', before_hash, 'PARAM_DELTA_VERIFIED', round(delta, 6), flush=True)
    print('PAIRED_SCENARIO_SEED', eval_seed, 'EPISODES', args.episodes, flush=True)
    per_episode = {}
    summaries = {}
    for mode in MODES:
        r = evaluate_mode(mode, args.episodes, eval_seed, max_steps,
                          untrained, trained)
        per_episode[mode] = r
        summaries[mode] = describe(r)
        print('POLICY', mode, json.dumps(summaries[mode], sort_keys=True), flush=True)
    comparisons = {
        'trained_sampled_minus_untrained_sampled': paired_differences(
            per_episode['trained_sampled'], per_episode['untrained_sampled']),
        'trained_greedy_minus_untrained_greedy': paired_differences(
            per_episode['trained_greedy'], per_episode['untrained_greedy']),
        'trained_sampled_minus_drive_forward': paired_differences(
            per_episode['trained_sampled'], per_episode['drive_forward']),
    }
    print('PAIRED_COMPARISONS', json.dumps(comparisons, sort_keys=True), flush=True)
    after_hash = sha256(ckpt)
    if before_hash != after_hash:
        raise RuntimeError('Input checkpoint SHA256 changed during evaluation')
    report = dict(schema_version=1, purpose='read-only independent evaluation',
                  warnings=['Solo shooting, stationary ball, and near-aligned spawn are NOT competitive RL',
                            'No training occurs in this script; result does not transfer to Cycle 9',
                            'Bootstrap intervals describe these paired spawn scenarios, not generalization'],
                  checkpoint=str(ckpt), checkpoint_sha256=after_hash,
                  seed=seed, eval_seed=eval_seed, episodes=args.episodes,
                  reconstructed_param_delta_l2=delta, summaries=summaries,
                  comparisons=comparisons)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Do not replace even a preexisting report. No checkpoint is written.
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print('SAVED_READ_ONLY_EVAL', out, flush=True)
    print('SUMMARY', json.dumps({'trained':summaries['trained_sampled'],
                                  'untrained':summaries['untrained_sampled'],
                                  'drive_forward':summaries['drive_forward'],
                                  'trained_minus_untrained':comparisons['trained_sampled_minus_untrained_sampled']},
                                 sort_keys=True), flush=True)
    print('CYCLE 9, ORIGINAL REPLAYS AND CHECKPOINT WERE NOT MODIFIED', flush=True)


if __name__ == '__main__':
    main()
