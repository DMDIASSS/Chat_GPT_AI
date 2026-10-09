"""Watch an existing Chat GPT AI PPO checkpoint play 1v1 in RLViser.

This runs inference only. No training and no modification of saved checkpoints.
"""
import argparse
import time

import numpy as np

from chatgpt_ai.config import PRESETS, TICK_SKIP
from chatgpt_ai.env import make_action_parser, make_obs, make_rewards
from chatgpt_ai.curriculum import ChatGPTCurriculum
from chatgpt_ai.policy import LoadedPolicy, find_latest_policy


def build_watch_env(preset: str):
    from rlgym.api import RLGym
    from rlgym.rocket_league.done_conditions import (
        AnyCondition,
        GoalCondition,
        NoTouchTimeoutCondition,
        TimeoutCondition,
    )
    from rlgym.rocket_league.rlviser import RLViserRenderer
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import (
        FixedTeamSizeMutator,
        MutatorSequence,
    )

    return RLGym(
        state_mutator=MutatorSequence(
            FixedTeamSizeMutator(blue_size=1, orange_size=1),
            ChatGPTCurriculum(preset),
        ),
        obs_builder=make_obs(),
        action_parser=make_action_parser(),
        reward_fn=make_rewards(preset),
        termination_cond=GoalCondition(),
        truncation_cond=AnyCondition(
            NoTouchTimeoutCondition(timeout_seconds=25),
            TimeoutCondition(timeout_seconds=180),
        ),
        transition_engine=RocketSimEngine(),
        renderer=RLViserRenderer(tick_rate=120 / TICK_SKIP),
    )


def main():
    p = argparse.ArgumentParser(description='Watch Chat GPT AI in lightweight RLViser')
    p.add_argument('--checkpoint', default=None, help='Optional path to PPO_POLICY.pt')
    p.add_argument('--preset', choices=PRESETS, default='smoke')
    p.add_argument('--speed', type=float, default=1.0,
                   help='Playback speed multiplier, default 1.0')
    p.add_argument('--sample', action='store_true',
                   help='Sample from action probabilities instead of using argmax')
    args = p.parse_args()
    if args.speed <= 0:
        p.error('--speed must be positive')

    checkpoint = args.checkpoint or find_latest_policy()
    model = LoadedPolicy(checkpoint)
    print('Loaded checkpoint:', model.path, flush=True)
    print('Playing smoke-test policy in 1v1 self-play (inference only).', flush=True)
    print('Use Ctrl+C in this terminal to exit.', flush=True)

    # Windows: run from the project folder containing rlviser.exe.
    env = build_watch_env(args.preset)
    delay = TICK_SKIP / 120.0 / args.speed

    try:
        observations = env.reset()
        env.render()
        while True:
            started = time.perf_counter()
            actions = {}
            for agent, obs in observations.items():
                flat_obs = np.asarray(obs, dtype=np.float32).reshape(-1)
                if len(flat_obs) != model.obs_count:
                    raise ValueError(
                        f'Checkpoint expects {model.obs_count} observation values, '
                        f'got {len(flat_obs)} for agent {agent}.'
                    )
                if args.sample:
                    import torch
                    with torch.no_grad():
                        idx, _ = model.policy.get_action(flat_obs, deterministic=False)
                        idx = int(idx.item())
                    actions[agent] = np.array([idx], dtype=np.int32)
                else:
                    actions[agent] = model.act(flat_obs)

            observations, _, terminated, truncated = env.step(actions)
            env.render()
            if any(terminated.values()) or any(truncated.values()):
                observations = env.reset()
                env.render()
            time.sleep(max(0.0, delay - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        print('\nViewer stopped.')
    finally:
        env.close()


if __name__ == '__main__':
    main()
