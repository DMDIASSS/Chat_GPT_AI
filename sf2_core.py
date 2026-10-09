"""SkillForge 2: one-car, goal-aligned forward wavedash experiment.

This is *not* the Nexto policy. It searches scripted 120 Hz controller
sequences, requiring a real dodge-ground contact. Never edits checkpoints.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Optional

import numpy as np

TICK_RATE = 120
ZERO = np.zeros(8, dtype=np.float32)
FORWARD = np.array([0., 1., 0.], dtype=np.float64)
CONTROLS = ('throttle', 'steer', 'pitch', 'yaw', 'roll', 'jump', 'boost', 'handbrake')


def orientation(forward, up=(0., 0., 1.)):
    f = np.asarray(forward, dtype=np.float64).copy()
    f /= np.linalg.norm(f)
    up = np.asarray(up, dtype=np.float64)
    right = np.cross(up, f)
    right /= np.linalg.norm(right)
    upper = np.cross(f, right)
    upper /= np.linalg.norm(upper)
    return np.column_stack([f, right, upper])


def set_scenario(state, car_id, seed: int, nose: float = 0.16):
    """Blue car moving toward a visible ball. No other car exists.

    nose > 0 pitches forward axis upward; makes landing geometry observable.
    The ball is a visual *waypoint*, not a wavedash success target.
    """
    c = state.cars[car_id]
    rng = np.random.default_rng(int(seed))
    px = float(rng.uniform(-170., 170.))
    py = -1350.
    height = float(rng.uniform(116., 172.))
    speed = float(rng.uniform(480., 810.))
    fall = float(rng.uniform(-440., -300.))
    forward = np.array([0., 1., float(nose)])
    c.physics.position = np.array([px, py, height])
    c.physics.rotation_mtx = orientation(forward)
    c.physics.linear_velocity = np.array([0., speed, fall])
    c.physics.angular_velocity = np.zeros(3)
    c.on_ground = False
    c.wheels_with_contact = (False, False, False, False)
    c.boost_amount = 0.
    c.has_jumped = True
    c.is_holding_jump = False
    c.is_jumping = False
    c.has_flipped = False
    c.has_double_jumped = False
    c.is_flipping = False
    c.air_time_since_jump = 0.22
    c.jump_time = 0.
    c.flip_time = 0.
    c.flip_torque = np.zeros(3)
    c.is_autoflipping = False
    c.autoflip_timer = 0.
    c.autoflip_direction = 0.
    # The ball is exactly downfield, far enough to avoid affecting the drill.
    state.ball.position = np.array([px, py + 1800., 93.])
    state.ball.linear_velocity = np.zeros(3)
    state.ball.angular_velocity = np.zeros(3)
    return FORWARD.copy()


class SoloSimulator:
    def __init__(self):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
        self.engine = RocketSimEngine(rlbot_delay=False)
        self.one = FixedTeamSizeMutator(blue_size=1, orange_size=0)
        self.ours = None
        self.forward = FORWARD.copy()
        self.state = None

    def reset(self, seed=700, nose=0.16):
        base = self.engine.create_base_state()
        self.one.apply(base, {})
        if len(base.cars) != 1:
            raise RuntimeError('Expected precisely 1 car in one-car mutator')
        self.ours = next(iter(base.cars))
        self.forward = set_scenario(base, self.ours, int(seed), nose)
        self.state = self.engine.set_state(base, {})
        if len(self.state.cars) != 1:
            raise RuntimeError('RocketSim returned more than 1 car')
        return self.state

    def step(self, action):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (8,) or not np.isfinite(action).all() or (np.abs(action) > 1.).any():
            raise ValueError('Invalid 8-control action')
        self.state = self.engine.step({self.ours: action[None, :]}, {})
        return self.state

    def close(self):
        self.engine.close()


@dataclass(frozen=True)
class Script:
    threshold: float = 38.
    nose: float = 0.16
    cancel_ticks: int = 16
    initial_pitch: float = 0.
    # pitch=-1 is a forward dodge in RocketSim: dodgeDir.x = -controls.pitch.
    dodge_pitch: float = -1.


class HeightTriggeredDodge:
    """One jump-press during descent, flip cancel immediately after release."""
    def __init__(self, script: Script):
        self.script = script
        self.phase = 'approach'
        self.fliptick: Optional[int] = None
        self.tick = 0

    def action(self, car):
        t = self.tick
        self.tick += 1
        a = ZERO.copy()
        if self.phase == 'approach':
            if (not car.on_ground and not car.has_flipped and car.physics.linear_velocity[2] < 0.
                    and car.physics.position[2] <= self.script.threshold):
                self.phase = 'cancel'
                self.fliptick = t
                a[2] = self.script.dodge_pitch
                a[5] = 1.
            else:
                a[2] = self.script.initial_pitch
        elif self.phase == 'cancel':
            if t - self.fliptick <= self.script.cancel_ticks:
                a[2] = -self.script.dodge_pitch
        return a


@dataclass
class Metrics:
    success: bool = False
    reason: str = 'not_started'
    dodge: bool = False
    jumped_airborne: bool = False
    landing_during_dodge: bool = False
    landed_upright: bool = False
    gained_speed: bool = False
    boost_free: bool = True
    flipped_full_rotation: bool = False
    used_no_driving_controls: bool = True
    dodge_tick: Optional[int] = None
    ground_tick: Optional[int] = None
    impulse_gain: float = 0.
    final_speed: float = 0.
    initial_speed: float = 0.
    rotation_before_landing_deg: float = 0.
    lowest_center_z: float = 1.e9
    contact_wheels: int = 0
    max_height: float = 0.
    total_ticks: int = 0
    fitness: float = 0.


class Detector:
    def __init__(self, state, car_id, max_ticks=115):
        self.car_id = car_id
        c = state.cars[car_id]
        self.metrics = Metrics(initial_speed=float(c.physics.linear_velocity[1]),
                               lowest_center_z=float(c.physics.position[2]),
                               max_height=float(c.physics.position[2]))
        self.prev_ground = bool(c.on_ground)
        self.prev_flipped = bool(c.has_flipped)
        self.prev_is_flipping = bool(c.is_flipping)
        self.prev_speed = float(c.physics.linear_velocity[1])
        self.done = False
        self.max_ticks = max_ticks
        self.grounded = 0
        self.near_flip_z: Optional[float] = None
        self.dodge_while_airborne = False

    def observe(self, state, action):
        if self.done:
            return self.metrics
        m = self.metrics
        m.total_ticks += 1
        car = state.cars[self.car_id]
        z = float(car.physics.position[2])
        up = float(car.physics.rotation_mtx[2, 2])
        speed = float(car.physics.linear_velocity[1])
        m.lowest_center_z = min(z, m.lowest_center_z)
        m.max_height = max(z, m.max_height)
        if abs(action[0]) > 1e-6 or abs(action[1]) > 1e-6 or abs(action[6]) > 1e-6 or abs(action[7]) > 1e-6:
            m.used_no_driving_controls = False
        if abs(action[6]) > 1e-6 or float(car.boost_amount) < -.05:
            m.boost_free = False
        if not m.ground_tick:
            m.rotation_before_landing_deg += math.degrees(float(np.linalg.norm(car.physics.angular_velocity))) / TICK_RATE
        if not self.prev_flipped and car.has_flipped:
            m.dodge = True
            m.dodge_tick = m.total_ticks
            self.dodge_while_airborne = not bool(car.on_ground)
            m.jumped_airborne = self.dodge_while_airborne
            self.near_flip_z = z
            m.impulse_gain = speed - self.prev_speed
        if not self.prev_ground and car.on_ground and m.ground_tick is None:
            m.ground_tick = m.total_ticks
            m.landing_during_dodge = bool(
                m.dodge and m.dodge_tick is not None
                and 0 <= m.ground_tick-m.dodge_tick <= 10
                and (self.prev_flipped or self.prev_is_flipping))
            m.contact_wheels = sum(bool(x) for x in car.wheels_with_contact)
        if m.ground_tick is not None and car.on_ground and up > 0.70:
            self.grounded += 1
        elif m.ground_tick is not None:
            self.grounded = 0
        m.final_speed = speed
        m.landed_upright = self.grounded >= 4
        m.gained_speed = (m.final_speed - m.initial_speed) >= 95.
        m.flipped_full_rotation = m.rotation_before_landing_deg > 245.
        m.fitness = (2*int(m.dodge) + 4*int(m.landing_during_dodge)
                     + 2*int(m.landed_upright)
                     + min(2., max(-1., (m.final_speed - m.initial_speed) / 130.))
                     - 2*int(m.flipped_full_rotation)
                     - 3*int(not m.used_no_driving_controls))
        m.success = bool(m.dodge and self.dodge_while_airborne
                         and m.dodge_tick is not None and self.near_flip_z is not None
                         and self.near_flip_z <= 85.
                         and m.landing_during_dodge and m.landed_upright
                         and m.contact_wheels >= 3
                         and m.gained_speed and not m.flipped_full_rotation
                         and m.boost_free and m.used_no_driving_controls)
        if m.success:
            m.reason = 'candidate_wavedash_physics_checks_passed'
            m.fitness += 10.
            self.done = True
        elif m.total_ticks >= self.max_ticks:
            m.reason = self.failure_reason()
            self.done = True
        self.prev_ground = bool(car.on_ground)
        self.prev_flipped = bool(car.has_flipped)
        self.prev_is_flipping = bool(car.is_flipping)
        self.prev_speed = speed
        return m

    def failure_reason(self):
        m = self.metrics
        if not m.dodge: return 'no_dodge_before_landing'
        if not self.dodge_while_airborne: return 'dodge_after_grounded'
        if self.near_flip_z is None or self.near_flip_z > 85: return 'dodge_too_high'
        if not m.landing_during_dodge: return 'no_ground_contact_during_dodge'
        if not m.landed_upright: return 'landed_unstable'
        if m.flipped_full_rotation: return 'full_flip_not_wavedash'
        if not m.gained_speed: return 'insufficient_forward_speed_gain'
        if not m.boost_free or not m.used_no_driving_controls: return 'other_movement_controls_used'
        return 'not_verified'


def rollout(sim, seed, script: Script, max_ticks=115):
    s = sim.reset(seed, script.nose)
    ctrl = HeightTriggeredDodge(script)
    det = Detector(s, sim.ours, max_ticks)
    for _ in range(max_ticks):
        act = ctrl.action(s.cars[sim.ours])
        s = sim.step(act)
        det.observe(s, act)
        if det.done: break
    return det.metrics


def metrics_json(m):
    return asdict(m)
