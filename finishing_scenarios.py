"""Physically plausible starting *opportunities*; not recorded human replays.

Every run starts from RLGym KickoffMutator, then repositions cars and ball.
Side-mirrored opportunities avoid training only blue or only orange attack.
"""
from __future__ import annotations
import random
import numpy as np
from chatgpt_ai.math_utils import facing_matrix

SCENARIOS = ('ground_finish', 'flick_setup', 'backboard_setup', 'defender_block')


def configure_shot(state, our_orange: bool, kind: str, rng=random) -> None:
    if kind not in SCENARIOS:
        raise ValueError(f'Unknown shot scenario: {kind}')
    ours = next(c for c in state.cars.values() if bool(c.is_orange) == our_orange)
    opponent = next(c for c in state.cars.values() if bool(c.is_orange) != our_orange)
    attack = -1.0 if our_orange else 1.0
    x = rng.uniform(-1250, 1250)
    side = -1.0 if rng.random() < 0.5 else 1.0
    y = rng.uniform(900, 2550) * attack
    ball = np.array([x, y, 115.0], dtype=float)
    vel = np.array([rng.uniform(-180, 180), attack * rng.uniform(120, 600), 0.0], dtype=float)
    our_pos = ball + np.array([rng.uniform(-250, 250), -attack * rng.uniform(320, 690), -98.0])
    enemy_pos = ball + np.array([side * rng.uniform(450, 1200), attack * rng.uniform(1000, 2000), -98.0])
    if kind == 'flick_setup':
        ball[2] = rng.uniform(125, 225)
        vel[1] = attack * rng.uniform(100, 330)
        our_pos = ball + np.array([rng.uniform(-65, 65), -attack * rng.uniform(150, 260), -108.0])
        enemy_pos = ball + np.array([side * rng.uniform(100, 450), attack * rng.uniform(650, 1050), -105.0])
    elif kind == 'backboard_setup':
        ball[1] = attack * rng.uniform(2900, 3700)
        ball[2] = rng.uniform(460, 1000)
        vel = np.array([rng.uniform(-220, 220), attack * rng.uniform(500, 1000), rng.uniform(-80, 260)])
        our_pos = ball + np.array([rng.uniform(-350, 350), -attack * rng.uniform(550, 950), -rng.uniform(350, 850)])
        enemy_pos = np.array([side * rng.uniform(600, 1600), attack * rng.uniform(4000, 4750), 17.0])
    elif kind == 'defender_block':
        enemy_pos = ball + np.array([rng.uniform(-280, 280), attack * rng.uniform(440, 650), -98.0])
        vel[1] = attack * rng.uniform(100, 380)
    # KickoffMutator puts both cars on their wheels; keep these starts grounded
    # instead of teleporting a ground-state car into the air without jump flags.
    our_pos[2] = 17.0
    enemy_pos[2] = 17.0
    our_pos[0] = float(np.clip(our_pos[0], -3700, 3700))
    enemy_pos[0] = float(np.clip(enemy_pos[0], -3700, 3700))
    enemy_pos[1] = float(np.clip(enemy_pos[1], -4800, 4800))

    state.ball.position = ball
    state.ball.linear_velocity = vel
    state.ball.angular_velocity = np.zeros(3)
    for car, pos, look_at, boost in (
        (ours, our_pos, ball, rng.uniform(45, 100)),
        (opponent, enemy_pos, ball, rng.uniform(30, 90))):
        car.physics.position = pos
        car.physics.linear_velocity = np.zeros(3)
        car.physics.angular_velocity = np.zeros(3)
        car.physics.rotation_mtx = facing_matrix(np.asarray(look_at) - pos)
        car.boost_amount = boost
