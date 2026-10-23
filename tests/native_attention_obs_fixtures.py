"""Actual RocketSim states for cross-language attention observation checks.

The JSON records simulator outputs, not separately reconstructed C++ rollouts.
That isolates observation semantics from the pinned simulators' version gap.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def rotation(yaw, pitch=0., roll=0.):
    cy, sy, cp, sp, cr, sr = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch), np.cos(roll), np.sin(roll)
    return np.asarray([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                       [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr],
                       [-sp, cp*sr, cp*cr]], dtype=np.float32)


def serial_state(state, previous, name):
    from afk_team_research import encode_multi
    from slater_team_env import TeamObserver
    _, ordered = encode_multi(state)
    # Intentionally unrelated to canonical order; preserves the real labels.
    ids = {aid: 19 + i*13 for i, aid in enumerate(reversed(ordered))}
    cars = []
    for aid, car in reversed(list(state.cars.items())):
        row = {'agent_id': str(aid), 'car_id': ids[aid], 'is_orange': bool(car.is_orange),
               'position': car.physics.position.tolist(), 'linear_velocity': car.physics.linear_velocity.tolist(),
               'angular_velocity': car.physics.angular_velocity.tolist(), 'rotation_mtx': car.physics.rotation_mtx.tolist(),
               'boost_amount': float(car.boost_amount), 'is_demoed': bool(car.is_demoed), 'on_ground': bool(car.on_ground),
               'has_double_jumped': bool(car.has_double_jumped), 'has_flipped': bool(car.has_flipped),
               'air_time_since_jump': float(car.air_time_since_jump)}
        if aid in previous:
            row['previous'] = previous[aid].tolist()
        cars.append(row)
    payload = {'name': name, 'cars': cars, 'boost_pad_timers': state.boost_pad_timers.tolist(),
               'ball': {'position': state.ball.position.tolist(), 'linear_velocity': state.ball.linear_velocity.tolist(),
                        'angular_velocity': state.ball.angular_velocity.tolist()}}
    return payload, TeamObserver().observe(state, previous)


def real_states():
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    from nexto_teacher import nexto_actions
    rng = np.random.default_rng(384712)
    engine = RocketSimEngine(rlbot_delay=True)
    saved_random = random.getstate()
    random.seed(384712)
    actions = nexto_actions()
    frames, expected = [], []
    stages = ('kickoff', 'ground', 'airborne', 'upside_down', 'demo', 'boost_cooldowns')
    try:
        for blue in range(1, 4):
            for orange in range(1, 4):
                for stage in stages:
                    initial = engine.create_base_state()
                    FixedTeamSizeMutator(blue_size=blue, orange_size=orange).apply(initial, {})
                    KickoffMutator().apply(initial, {})
                    # Deliberately exercise lexical rather than numeric agent ordering.
                    initial.cars = {f'{"orange" if car.is_orange else "blue"}-{(10, 2, 1)[int(aid.split("-")[-1])]}': car
                                    for aid, car in initial.cars.items()}
                    if stage != 'kickoff':
                        initial.ball.position = np.array([rng.uniform(-1500, 1500), rng.uniform(-2200, 2200), rng.uniform(93, 1300)], np.float32)
                        initial.ball.linear_velocity = rng.uniform(-1800, 1800, 3).astype(np.float32)
                        initial.ball.angular_velocity = rng.uniform(-4.5, 4.5, 3).astype(np.float32)
                        for i, car in enumerate(initial.cars.values()):
                            flying = stage in ('airborne', 'upside_down')
                            car.physics.position = np.array([rng.uniform(-2800, 2800), rng.uniform(-3600, 3600), rng.uniform(250, 1300) if flying else 17], np.float32)
                            car.physics.linear_velocity = rng.uniform(-1700, 1700, 3).astype(np.float32)
                            car.physics.angular_velocity = rng.uniform(-4.5, 4.5, 3).astype(np.float32)
                            # Trace-positive plus x/y/z dominant quaternion branches.
                            yaw, pitch, roll = ((.17, -.2, .3), (0, 0, np.pi), (0, np.pi, 0), (np.pi, 0, 0))[i % 4]
                            if stage == 'upside_down': roll = np.pi
                            car.physics.rotation_mtx = rotation(yaw, pitch, roll)
                            car.boost_amount = float(rng.uniform(0, 100))
                            car.on_ground = not flying
                            car.has_jumped = flying
                            car.air_time_since_jump = (0., .8, 1.249, 1.251)[i % 4]
                            car.has_flipped = flying and i % 3 == 1
                            car.has_double_jumped = flying and i % 3 == 2
                            if stage == 'demo' and i % 2 == 0:
                                car.demo_respawn_timer = 1.4 + i * .1
                        if stage == 'boost_cooldowns':
                            initial.boost_pad_timers[:] = np.resize(np.array([0., 1e-7, 1e-6, 1.0001e-6, 3.1, 8.9], np.float32), 34)
                    state = engine.set_state(initial, {})
                    previous = {aid: actions[(i*17 + blue*11 + orange*3) % 90].copy() for i, aid in enumerate(state.cars)}
                    # Missing prior command should become exactly eight zeros.
                    previous.pop(next(iter(previous)))
                    name = f'{blue}v{orange}_{stage}_before'
                    frame, views = serial_state(state, previous, name)
                    frames.append(frame); expected.append(views)
                    applied = {aid: actions[(i*23 + orange*7) % 90].copy() for i, aid in enumerate(state.cars)}
                    state = engine.step({aid: np.tile(control, (8, 1)) for aid, control in applied.items()}, {})
                    frame, views = serial_state(state, applied, f'{blue}v{orange}_{stage}_after8ticks')
                    frames.append(frame); expected.append(views)
    finally:
        random.setstate(saved_random)
        # Current RocketSimEngine exposes no close(); the owning arena is freed.
        del engine
    return {'states': frames}, expected


def write_fixtures(path: Path):
    payload, expected = real_states()
    Path(path).write_text(json.dumps(payload), encoding='utf-8')
    return payload, expected


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    payload, _ = write_fixtures(args.output)
    print(json.dumps({'states': len(payload['states']), 'output': str(args.output)}))
