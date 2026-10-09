"""Compare a saved PPO policy's actions against reconstructed human actions.
Run from the Chat_GPT_AI project folder using its virtual environment.
This is inference-only and will not modify checkpoints or datasets.
"""
import argparse
from pathlib import Path

import numpy as np
import torch

from chatgpt_ai.policy import LoadedPolicy, find_latest_policy
from rlgym.rocket_league.action_parsers import LookupTableAction


def report(name: str, indexes: np.ndarray, table: np.ndarray) -> None:
    controls = table[indexes]
    print(f"\n{name}: {len(indexes):,} decisions")
    for label, col, test in (
        ("jump", 5, lambda x: x > 0),
        ("boost", 6, lambda x: x > 0),
        ("forward throttle", 0, lambda x: x > 0),
        ("reverse throttle", 0, lambda x: x < 0),
        ("handbrake", 7, lambda x: x > 0),
    ):
        print(f"  {label:18}: {100.0 * np.mean(test(controls[:, col])):6.2f}%")
    values, counts = np.unique(indexes, return_counts=True)
    top = np.argsort(-counts)[:5]
    print("  top action IDs:     " + ", ".join(f"{values[i]} ({100.0*counts[i]/len(indexes):.1f}%)" for i in top))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', default='data/datasets/human_1v1.npz')
    p.add_argument('--checkpoint', default=None)
    p.add_argument('--samples', type=int, default=3000)
    args = p.parse_args()
    if args.samples <= 0:
        p.error('--samples must be positive')
    dataset = np.load(args.dataset)
    obs, human = dataset['obs'], dataset['actions'].astype(np.int64)
    model = LoadedPolicy(args.checkpoint or find_latest_policy())
    table = np.asarray(LookupTableAction.make_lookup_table())
    if obs.ndim != 2 or obs.shape[1] != model.obs_count:
        raise ValueError(f'Dataset obs shape {obs.shape} does not match policy input {model.obs_count}')
    if human.min() < 0 or human.max() >= len(table):
        raise ValueError(f'Human action IDs outside action table: {human.min()}..{human.max()}')
    if len(table) != model.action_count:
        raise ValueError('PPO policy and LookupTableAction have different action counts')
    random = np.random.default_rng(42)
    selected = random.choice(len(obs), size=min(args.samples, len(obs)), replace=False)
    sample = []
    greedy = []
    with torch.no_grad():
        for pos in selected:
            o = np.asarray(obs[pos], dtype=np.float32)
            sampled, _ = model.policy.get_action(o, deterministic=False)
            greedy_action, _ = model.policy.get_action(o, deterministic=True)
            sample.append(int(sampled.item()))
            greedy.append(int(greedy_action.item()))
    print('Checkpoint:', model.path)
    print('NOTE: This compares actions on recorded HUMAN states, not states reached during PPO self-play.')
    report('Reconstructed humans', human[selected], table)
    report('Current PPO (sampled)', np.asarray(sample, dtype=np.int64), table)
    report('Current PPO (greedy)', np.asarray(greedy, dtype=np.int64), table)
    print('\nNo files changed.')


if __name__ == '__main__':
    main()
