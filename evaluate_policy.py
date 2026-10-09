"""Inspect a checkpoint's network and sample actions. NOT a Nexto win-rate test."""
import argparse
from pathlib import Path
import numpy as np
from chatgpt_ai.policy import LoadedPolicy, find_latest_policy


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--checkpoint', type=Path)
    args = p.parse_args()
    model = LoadedPolicy(args.checkpoint or find_latest_policy())
    print('Checkpoint:', model.path)
    print('Input observation size:', model.obs_count)
    print('Actions:', model.action_count)
    # Only demonstrates local inference, does not measure playing skill.
    print('Output for zero-valued observation:', model.act(np.zeros(model.obs_count, dtype=np.float32)))
    print('To evaluate skill, use an RLBot v5 offline match against Nexto (see docs/BENCHMARK.md).')


if __name__ == '__main__':
    main()
