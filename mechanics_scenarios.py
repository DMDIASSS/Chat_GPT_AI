"""RocketSim v2 mechanics scenarios for the original Nexto observation space.

Scenarios are bounded starts, not scripted mechanics. Success is measured later.
The first four have grounded skill definitions. The advanced tasks are exploratory.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

STAGES = ('recovery', 'wavedash', 'kickoff', 'aerial_touch',
          'air_dribble', 'flip_reset', 'double_tap', 'ground_pinch',
          'wall_pinch', 'ceiling_touch')
INTRO = ('recovery', 'wavedash', 'kickoff', 'aerial_touch')
BALL_R = 92.75


def norm(v):
    a = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-8 else np.array([0., 1., 0.])


def basis(forward, up=(0, 0, 1)):
    """PhysicsObject.rotation_mtx has LOCAL basis in COLUMNS (forward,right,up)."""
    f = norm(forward)
    u = norm(up)
    right = np.cross(u, f)
    if np.linalg.norm(right) < 1e-7:
        u = np.array([0., 1., 0.])
        right = np.cross(u, f)
    right = norm(right)
    up_final = norm(np.cross(f, right))
    return np.column_stack((f, right, up_final))


def set_car(car, pos, toward, *, speed=0., v_z=0., boost=60.,
            up=(0, 0, 1), on_ground=False, spent_flip=False):
    pos = np.asarray(pos, dtype=np.float64)
    direction = norm(np.asarray(toward, dtype=np.float64) - pos)
    car.physics.position = pos
    car.physics.rotation_mtx = basis(direction, up)
    car.physics.linear_velocity = direction * speed + np.array([0., 0., v_z])
    car.physics.angular_velocity = np.zeros(3)
    car.boost_amount = float(boost)
    car.on_ground = on_ground
    car.has_jumped = bool(spent_flip)
    car.has_flipped = bool(spent_flip)
    car.has_double_jumped = False
    car.is_holding_jump = False
    car.is_jumping = False
    car.air_time_since_jump = 1.4 if spent_flip else 0.0
    car.flip_time = 0.4 if spent_flip else 0.0


def set_ball(ball, pos, vel):
    ball.position = np.array(pos, dtype=np.float64)
    ball.linear_velocity = np.array(vel, dtype=np.float64)
    ball.angular_velocity = np.zeros(3)


def configure(state, stage: str, ours, opponent, rng: np.random.Generator):
    """Mutate a *fresh, kickoff-initialized* v2 GameState. Never changes team IDs."""
    if stage not in STAGES:
        raise ValueError(f'Unknown mechanic {stage!r}')
    us = state.cars[ours]
    them = state.cars[opponent]
    attack = -1. if us.is_orange else 1.
    x = float(rng.uniform(-750, 750))
    y = float(rng.uniform(-1300, 1300))
    s = float(rng.choice((-1., 1.)))
    if stage == 'kickoff':
        # KickoffMutator already applied. Do not perturb valid kickoff spawns.
        return
    elif stage == 'recovery':
        # Low-boost, tilted midair car; land wheels down without losing speed.
        z = float(rng.uniform(280, 550))
        set_car(us, [x, y, z], [x + 800*s, y + 800*attack, 50],
                up=[s*.7, 0.25, -0.55], speed=float(rng.uniform(280, 700)),
                v_z=float(rng.uniform(-450, -100)), boost=25, spent_flip=True)
        set_ball(state.ball, [2100*s, 800*attack, 93.], [0, 0, 0])
    elif stage == 'wavedash':
        # Sideways/forward midair descent, initially with a dodge available.
        z = float(rng.uniform(135, 200))
        set_car(us, [x, y, z], [x+120*s, y+800*attack, z-8],
                up=[0.0, -0.2*attack, 1.], speed=float(rng.uniform(650, 1000)),
                v_z=float(rng.uniform(-250, -110)), boost=5)
        set_ball(state.ball, [2300*s, 2300*attack, 93], [0, 0, 0])
    elif stage == 'aerial_touch':
        z = float(rng.uniform(550, 1150))
        bp = [x, y+attack*350, z]
        cp = [x+float(rng.uniform(-250, 250)), y-attack*650, z-400]
        set_ball(state.ball, bp, [0, attack*450, float(rng.uniform(-100, 150))])
        set_car(us, cp, bp, speed=float(rng.uniform(250, 650)), boost=90)
    elif stage == 'air_dribble':
        z = float(rng.uniform(390, 800))
        bp = [x, y+attack*260, z]
        set_ball(state.ball, bp, [0, attack*520, 120])
        set_car(us, [x, y-attack*145, z-155], bp, speed=450, v_z=125, boost=90)
    elif stage == 'flip_reset':
        # Put a flip-spent car near a floating ball, wheels roughly facing it.
        z = float(rng.uniform(500, 930))
        bp = np.array([x, y, z])
        cp = bp + np.array([0., -attack*135., 105.])
        set_ball(state.ball, bp, [0, attack*300, -90])
        set_car(us, cp, bp, speed=180, v_z=-80, boost=70,
                up=(0, 0, -1), spent_flip=True)
    elif stage == 'double_tap':
        z = float(rng.uniform(700, 1350))
        goal_y = attack * 5120
        bp = np.array([x, goal_y-attack*520, z])
        set_ball(state.ball, bp, [0, attack*1050, 170])
        cp = bp + np.array([0., -attack*520., -130.])
        set_car(us, cp, bp, speed=800, boost=85)
    elif stage == 'ground_pinch':
        bp = [x, y, BALL_R + 1]
        set_ball(state.ball, bp, [0, attack*150, 0])
        set_car(us, [x+180*s, y-attack*180, 35], bp,
                speed=float(rng.uniform(700, 1300)), boost=60, on_ground=True)
    elif stage == 'wall_pinch':
        wx = s * 4096
        bp = [wx-s*115, y, float(rng.uniform(220, 550))]
        set_ball(state.ball, bp, [0, attack*380, -80])
        cp = [wx-s*430, y-attack*230, bp[2]-100]
        set_car(us, cp, bp, speed=900, boost=75)
    elif stage == 'ceiling_touch':
        z = float(rng.uniform(1150, 1600))
        bp = [x, y+attack*330, z]
        set_ball(state.ball, bp, [0, attack*440, -150])
        cp = [x, y-attack*270, 1940]
        set_car(us, cp, bp, up=(0, 0, -1), speed=450, boost=75)
    # Opponent held away for isolated mechanics to prevent reset contamination.
    # If opponent=Nexto in the trainer, its normal control resumes from this spawn.
    set_car(them, [2800*s, -attack*3500, 22], [0, 0, 110],
            boost=35, on_ground=True)
