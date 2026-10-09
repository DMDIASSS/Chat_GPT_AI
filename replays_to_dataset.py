"""Create behavior-cloning (observations, discrete actions) dataset from 1v1 .replay files.

Requires rlgym-tools. Reconstructed replay actions are *approximations*.
"""
import argparse
import numpy as np
from pathlib import Path
from chatgpt_ai.config import DATASET_PATH, ROOT


def convert(folder: Path, output: Path, every: int, max_samples: int) -> int:
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    from rlgym_tools.rocket_league.replays.pick_action import get_best_action_options
    from chatgpt_ai.env import make_obs

    table = LookupTableAction.make_lookup_table()
    observations, actions = [], []
    files = sorted(folder.rglob('*.replay'))
    if not files:
        raise FileNotFoundError(f'No .replay files under {folder}. Run fetch_replays.py or add yours.')
    for path in files:
        if len(actions) >= max_samples:
            break
        kept = 0
        try:
            replay = ParsedReplay.load(path)
            builder = make_obs()
            initialized = False
            for frame_index, frame in enumerate(replay_to_rlgym(replay)):
                if len(actions) >= max_samples:
                    break
                if frame_index % every != 0:
                    continue
                state = frame.state
                # IMPORTANT: trained bot has 2-car observations ONLY (1v1).
                if len(state.cars) != 2:
                    continue
                agents = list(state.cars)
                if not initialized:
                    builder.reset(agents, state, {})
                    initialized = True
                obs_dict = builder.build_obs(agents, state, {})
                for agent in agents:
                    if len(actions) >= max_samples:
                        break
                    action = frame.actions.get(agent)
                    if action is None:
                        continue
                    if frame.update_age.get(agent, 100.0) > .1:
                        continue  # unreliable/interpolated state
                    continuous = np.asarray(action, dtype=np.float32).reshape(-1)
                    if continuous.shape != (8,) or not np.isfinite(continuous).all():
                        continue
                    try:
                        # Better than naive L2: respects jump/dodge/boost feasibility.
                        probabilities = get_best_action_options(
                            state.cars[agent], continuous, table, greedy=True)
                        probabilities = np.asarray(probabilities)
                        if probabilities.shape != (len(table),) or not np.isfinite(probabilities).all():
                            continue
                        label = int(np.argmax(probabilities))
                    except (ValueError, AssertionError, IndexError):
                        continue
                    obs = np.asarray(obs_dict[agent], dtype=np.float32).reshape(-1)
                    if obs.shape != (92,) or not np.isfinite(obs).all():
                        continue
                    observations.append(obs)
                    actions.append(label)
                    kept += 1
            print(f'{path.name}: {kept} training samples')
        except Exception as e:
            print(f'{path.name}: FAILED: {type(e).__name__}: {e}')
            raise
    if not actions:
        raise RuntimeError('No valid 1v1 samples. Check replay format and parser dependencies.')
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, obs=np.stack(observations), actions=np.array(actions, dtype=np.int64))
    print(f'Saved {len(actions)} samples to {output}')
    return len(actions)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, default=ROOT / 'data' / 'replays')
    p.add_argument('--output', type=Path, default=DATASET_PATH)
    p.add_argument('--every', type=int, default=4)
    p.add_argument('--max-samples', type=int, default=300000)
    args = p.parse_args()
    if args.every < 1 or args.max_samples < 1:
        p.error('every and max-samples must be positive')
    convert(args.input, args.output, args.every, args.max_samples)


if __name__ == '__main__':
    main()
