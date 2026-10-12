"""Read-only v0.1.9 defender-car motion sanity check.

Place in E:\\Downloads\\Chat_GPT_AI (beside slater_research), run with the existing venv.
Does not write files, load policies or checkpoints, or start training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from slater_research.defender_reachability import policy_action
from slater_research.replay_engine import Clip
from slater_research.verified_defender_env import VerifiedDefenderEnv

POLICIES = ('replay', 'neutral', 'boost', 'boost_left', 'jump_boost', 'pursuit_left', 'pursuit_right')
DEFAULT_FILES = ('44464dc6600b06_goal000.npz', '9303f4d0cc27f2_goal008.npz')


def norm(a):
    return float(np.linalg.norm(np.asarray(a, dtype=np.float64)))


def rollout(clip, candidate, policy, engine_factory):
    engine = engine_factory()
    try:
        env = VerifiedDefenderEnv(clip, candidate, engine, train_only=True)
        if len(env.defenders) != 1:
            raise ValueError('Exactly one defender required')
        did = env.defenders[0]
        car = env.state.cars[did]
        pos0 = np.asarray(car.physics.position, dtype=np.float64).copy()
        demo0 = float(car.demo_respawn_timer)
        wheels0 = tuple(bool(x) for x in car.wheels_with_contact)
        jumping0 = bool(car.is_jumping)
        jump_time0 = float(car.jump_time)
        timeline = {env.i: pos0}
        nearest = norm(np.asarray(env.state.ball.position, float) - pos0)
        changed_actions = 0
        control_steps = 0
        while not env.done:
            original = env.replay_actions()
            proposed = policy_action(policy, env.state, did,
                                     step_index=env.i - env.start,
                                     replay_action=original[did])
            control_steps += 1
            if not np.allclose(proposed, original[did], atol=1e-6):
                changed_actions += 1
            env.step({did: proposed})
            carpos = np.asarray(env.state.cars[did].physics.position, dtype=np.float64).copy()
            timeline[env.i] = carpos
            nearest = min(nearest, norm(np.asarray(env.state.ball.position, float) - carpos))
        return {
            'policy': policy,
            'demo_timer_at_start': demo0,
            'wheels_at_start': wheels0,
            'is_jumping_at_start': jumping0,
            'jump_time_at_start': jump_time0,
            'start_position': pos0,
            'last_position': timeline[env.i],
            'total_movement': norm(timeline[env.i] - pos0),
            'changed_controls': changed_actions,
            'control_steps': control_steps,
            'nearest_ball_distance': nearest,
            'defender_touch': env.result().defender_touch_observed,
            'status': env.result().status,
            'timeline': timeline,
        }
    finally:
        engine.close()


def compare(reference, alternate):
    shared = reference['timeline'].keys() & alternate['timeline'].keys()
    return max((norm(alternate['timeline'][t] - reference['timeline'][t])
                for t in shared), default=float('nan'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips', default='data/replay_scenarios_smoke_v012')
    parser.add_argument('--catalog', default='data/replay_scenarios_smoke_v012/shot_catalog_v016.json')
    parser.add_argument('--files', nargs='+', default=list(DEFAULT_FILES))
    args = parser.parse_args()
    from rlgym.rocket_league.sim import RocketSimEngine
    def engine_factory():
        return RocketSimEngine(rlbot_delay=False)

    with Path(args.catalog).open('r', encoding='utf-8') as fp:
        catalog = json.load(fp)
    entries = {r['clip_file']: r for r in catalog['candidates']}
    for name in args.files:
        if name not in entries:
            raise ValueError(f'Not selected by verified gate: {name}')
        if entries[name]['split'] != 'train':
            raise ValueError(f'Not a training clip: {name}')
        print(f'\n== {name} (window={entries[name]["window_s"]}s) ==', flush=True)
        clip = Clip.load(Path(args.clips) / name)
        baseline = rollout(clip, entries[name], 'replay', engine_factory)
        print(f'Initial car: demo_timer={baseline["demo_timer_at_start"]:.2f}s '
              f'wheels={baseline["wheels_at_start"]} '
              f'is_jumping={baseline["is_jumping_at_start"]} '
              f'jump_time={baseline["jump_time_at_start"]:.3f}s', flush=True)
        for policy in POLICIES:
            row = baseline if policy == 'replay' else rollout(clip, entries[name], policy, engine_factory)
            delta = compare(baseline, row)
            print(f'{policy:14s} demo_start={row["demo_timer_at_start"]:5.2f}s '
                  f'changed_commands={row["changed_controls"]:2d}/{row["control_steps"]:2d} '
                  f'car_move={row["total_movement"]:7.1f}uu '
                  f'car_diversion_vs_replay={delta:7.1f}uu '
                  f'min_ball_car_distance={row["nearest_ball_distance"]:7.1f}uu '
                  f'touch={int(row["defender_touch"])} '
                  f'status={row["status"]}', flush=True)
    print('\nREAD ONLY: no checkpoint, PPO, report file or NPZ changes.', flush=True)


if __name__ == '__main__':
    main()
