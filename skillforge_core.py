"""SkillForge v1: physics-verified *forward* wavedash experiments (RLGym v2).

No existing Nexto policy is trained or overwritten. This module deliberately
rejects flips, normal landings, boosted speedups and full rotations. A result is
an experimental detector result, not proof of ranked competitive skill.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from typing import Optional
import numpy as np

TICK_RATE = 120
ZERO = np.zeros(8, dtype=np.float32)
# RLGym controls: throttle, steer, pitch, yaw, roll, jump, boost, handbrake
CONTROL_NAMES = ('throttle', 'steer', 'pitch', 'yaw', 'roll', 'jump', 'boost', 'handbrake')


def vec(x):
    return np.asarray(x, dtype=np.float64).reshape(3)


def rotation(forward, up=(0., 0., 1.)):
    f = vec(forward); f /= (np.linalg.norm(f) or 1)
    up = vec(up)
    r = np.cross(up, f)
    if np.linalg.norm(r) < 1e-5:
        r = np.cross(np.array([1., 0., 0.]), f)
    r /= (np.linalg.norm(r) or 1)
    u = np.cross(f, r); u /= (np.linalg.norm(u) or 1)
    return np.column_stack((f, r, u))


def configure_wavedash(state, agent, opponent, seed: int, difficulty: str = 'near'):
    """Spawn a descending jumped-but-not-dodged car with a dodge available.

    One-touch fixed-position practices are *not* wave dashes. We randomize
    height, lateral speed, car yaw/pitch and falling speed. First real-sim
    preflight checks the desired jump/flip flags survive set_state.
    """
    if difficulty not in ('near', 'varied'):
        raise ValueError('difficulty must be near or varied')
    rng = np.random.default_rng(int(seed))
    us = state.cars[agent]
    them = state.cars[opponent]
    side = float(rng.uniform(-1, 1))
    heading = np.array([0., 1. if not us.is_orange else -1., 0.])
    if difficulty == 'near':
        height = float(rng.uniform(105., 155.))
        fall = float(rng.uniform(-480., -300.))
        speed = float(rng.uniform(450., 830.))
        pitch = float(rng.uniform(-0.11, 0.20))
    else:
        height = float(rng.uniform(100., 240.))
        fall = float(rng.uniform(-520., -210.))
        speed = float(rng.uniform(300., 1050.))
        pitch = float(rng.uniform(-0.25, 0.32))
    yaw = float(rng.uniform(-0.10, 0.10))
    f = np.array([yaw, heading[1], pitch])
    f /= (np.linalg.norm(f) or 1)
    p = np.array([side * 800., -heading[1] * 1100., height])
    us.physics.position = p
    us.physics.rotation_mtx = rotation(f)
    us.physics.linear_velocity = np.array([side * 80., heading[1] * speed, fall])
    us.physics.angular_velocity = np.zeros(3)
    us.boost_amount = 0.
    us.on_ground = False
    us.has_jumped = True
    us.is_jumping = False
    us.is_holding_jump = False
    us.has_flipped = False
    us.has_double_jumped = False
    us.is_flipping = False
    us.air_time_since_jump = 0.20
    us.jump_time = 0.0
    us.flip_time = 0.0
    us.flip_torque = np.zeros(3)
    # Keep ball and passive opponent far from action: this is a motion drill.
    them.physics.position = np.array([2700., 3700. if not them.is_orange else -3700., 17.])
    them.physics.rotation_mtx = rotation([0., 1., 0.])
    them.physics.linear_velocity = np.zeros(3)
    them.physics.angular_velocity = np.zeros(3)
    them.boost_amount = 0.
    them.on_ground = True
    state.ball.position = np.array([2500., 2500., 93.])
    state.ball.linear_velocity = np.zeros(3)
    state.ball.angular_velocity = np.zeros(3)
    return heading


@dataclass
class DashMetrics:
    success: bool = False
    dodge_detected: bool = False
    dodge_near_ground: bool = False
    landed_during_dodge: bool = False
    wheels_down: bool = False
    boost_free: bool = True
    no_full_flip: bool = True
    speed_gain: float = 0.
    final_speed: float = 0.
    initial_speed: float = 0.
    flip_tick: Optional[int] = None
    landing_tick: Optional[int] = None
    tick: int = 0
    peak_height: float = 0.
    total_rotation_deg: float = 0.
    uprightness: float = 0.
    valid_spawn: bool = True
    reason: str = 'not_attempted'
    fitness: float = 0.


class WavedashDetector:
    """Tick-resolution detector with hard failure gates.

    Requires car.has_flipped transition while airborne, landing shortly after
    while RocketSim reports is_flipping or active flip_time; sufficient forward
    impulse, wheels-down settling, and no boost. A normal jump, front-flip in
    the air, or speedy landing without a dodge cannot score success.
    """
    def __init__(self, state, car_id, forward, *, max_ticks=110):
        c = state.cars[car_id]
        self.cid = car_id
        self.forward = vec(forward); self.forward /= np.linalg.norm(self.forward)
        self.max_ticks = max_ticks
        self.start_p = vec(c.physics.position)
        self.initial_velocity = vec(c.physics.linear_velocity)
        self.v_before_flip = float(np.dot(self.initial_velocity, self.forward))
        self.start_boost = float(c.boost_amount)
        self.previous_flipped = bool(c.has_flipped)
        self.previous_on_ground = bool(c.on_ground)
        self.previous_ang_vel = vec(c.physics.angular_velocity)
        self.dodge_started_airborne = False
        self.landing_velocity = 0.
        self.grounded_ticks = 0
        self.metrics = DashMetrics(initial_speed=self.v_before_flip,
            peak_height=float(self.start_p[2]),
            valid_spawn=(not c.on_ground and c.has_jumped and not c.has_flipped
                         and not c.is_holding_jump and float(c.air_time_since_jump) < 1.20))
        self.done = False

    def observe(self, state, action):
        if self.done:
            return self.metrics
        m = self.metrics
        m.tick += 1
        c = state.cars[self.cid]
        p = vec(c.physics.position); v = vec(c.physics.linear_velocity)
        omega = vec(c.physics.angular_velocity)
        m.peak_height = max(m.peak_height, float(p[2]))
        # Approximate integrated angular displacement, rather than only testing
        # the final orientation (a full flip can return to upright).
        m.total_rotation_deg += math.degrees(np.linalg.norm(omega)) / TICK_RATE
        if m.total_rotation_deg > 280.:
            m.no_full_flip = False
        up_z = float(c.physics.rotation_mtx[2, 2])
        m.uprightness = up_z
        m.final_speed = float(np.dot(v, self.forward))
        if float(action[6]) > 0.1 or float(c.boost_amount) < self.start_boost - 0.15:
            m.boost_free = False
        currently_flipped = bool(c.has_flipped)
        airborne = not bool(c.on_ground)
        if not self.previous_flipped and currently_flipped:
            m.dodge_detected = True
            self.dodge_started_airborne = airborne
            m.flip_tick = m.tick
            self.v_before_flip = float(np.dot(v, self.forward))
            m.dodge_near_ground = bool(airborne and p[2] <= 260. and v[2] < 90.)
        # Check the actual transition from air to wheel-supported ground.
        if (not self.previous_on_ground and c.on_ground and m.dodge_detected
              and m.landing_tick is None):
            m.landing_tick = m.tick
            # RocketSim may clear is_flipping on contact. Compare frame count
            # from flip activation and flag while on/just before landing.
            m.landed_during_dodge = bool(m.flip_tick is not None and
                 0 < m.tick-m.flip_tick <= 22 and
                 (currently_flipped or bool(c.is_flipping) or float(c.flip_time) > 0))
            self.landing_velocity = float(np.dot(v, self.forward))
        if m.landing_tick is not None and c.on_ground and up_z >= 0.70:
            self.grounded_ticks += 1
        elif m.landing_tick is not None:
            self.grounded_ticks = 0
        if self.grounded_ticks >= 5:
            m.wheels_down = True
        m.speed_gain = m.final_speed - m.initial_speed
        m.no_full_flip = m.no_full_flip and m.total_rotation_deg <= 280.
        # Early reward is only for exploration; NOT a success flag.
        m.fitness = (0.65*float(m.dodge_detected)
            + 0.9*float(m.dodge_near_ground)
            + 1.0*float(m.landed_during_dodge)
            + 0.65*float(m.wheels_down)
            + 0.0035*max(-100., min(450., m.speed_gain))
            + 0.3*max(-1., min(1., up_z))
            - 1.5*float(not m.no_full_flip)
            - 2.5*float(not m.boost_free)
            - 1.0*float(not m.valid_spawn))
        m.success = bool(m.valid_spawn and m.dodge_detected and
            self.dodge_started_airborne and m.dodge_near_ground and
            m.landed_during_dodge and m.wheels_down and
            m.boost_free and m.no_full_flip and m.speed_gain >= 105. and
            m.final_speed >= 350. and up_z >= .70)
        if m.success:
            m.fitness += 8.
            m.reason = 'verified_wavedash'
            self.done = True
        elif m.tick >= self.max_ticks:
            m.reason = self.failure_reason()
            self.done = True
        self.previous_flipped = currently_flipped
        self.previous_on_ground = bool(c.on_ground)
        self.previous_ang_vel = omega
        return m

    def failure_reason(self):
        m = self.metrics
        if not m.valid_spawn: return 'invalid_spawn'
        if not m.boost_free: return 'boost_used'
        if not m.no_full_flip: return 'full_flip_or_excess_spin'
        if not m.dodge_detected: return 'no_dodge'
        if not m.dodge_near_ground: return 'dodge_too_high'
        if not m.landed_during_dodge: return 'dodge_did_not_hit_ground'
        if not m.wheels_down: return 'unstable_landing'
        if m.speed_gain < 105.: return 'no_verified_speed_gain'
        return 'not_completed'


def macro_control(params, t, variant='forward'):
    """Action at physics tick t. Never throttle, steer, boost, handbrake.

    Forward: pitch + jump for dodge, then pitch flip cancel. Side: yaw and
    roll with jump, then corrective roll. Airroll-only cannot count a wavedash
    because without directional pitch/yaw it cannot initiate a useful dodge.
    """
    if variant not in ('forward', 'side', 'airroll_only'):
        raise ValueError(variant)
    delay = int(params['delay'])
    hold = int(params['hold'])
    cancel_delay = int(params['cancel_delay'])
    cancel_ticks = int(params['cancel_ticks'])
    pre = float(params.get('pre', 0.))
    post = float(params.get('post', 0.))
    c = np.zeros(8, dtype=np.float32)
    if t < delay:
        if variant == 'airroll_only': c[4] = pre
        elif variant == 'side': c[4] = pre
        else: c[2] = pre
    elif t < delay + hold:
        if variant == 'airroll_only': c[4] = pre
        elif variant == 'side':
            c[3] = float(params.get('direction', 1.)); c[4] = pre
        else: c[2] = float(params.get('direction', -1.))
        c[5] = 1. if variant != 'airroll_only' else 0.
    elif t < delay + hold + cancel_delay:
        if variant == 'side': c[3] = float(params.get('direction', 1.))
        elif variant == 'airroll_only': c[4] = pre
        else: c[2] = float(params.get('direction', -1.))
    elif t < delay + hold + cancel_delay + cancel_ticks:
        if variant == 'side': c[4] = -float(params.get('direction', 1.))
        elif variant == 'airroll_only': c[4] = -pre
        else: c[2] = -float(params.get('direction', -1.))
    else:
        if variant == 'side': c[4] = post
        elif variant == 'airroll_only': c[4] = post
        else: c[2] = post
    return c


def search_parameters(rng, mean=None, std=None):
    bounds = {'delay': (0, 22), 'hold': (1, 3), 'cancel_delay': (0, 8),
              'cancel_ticks': (2, 24), 'pre': (-0.8, 0.8),
              'post': (-0.8, 0.8)}
    p = {}
    for k,(lo,hi) in bounds.items():
        if mean is None:
            v = rng.uniform(lo, hi)
        else:
            v = rng.normal(mean[k], std[k])
        v = float(np.clip(v,lo,hi))
        p[k] = int(round(v)) if k in ('delay','hold','cancel_delay','cancel_ticks') else v
    p['direction'] = -1.  # forward flip: RL pitch=-1
    return p


def feature_vector(state, car_id, forward, tick):
    c = state.cars[car_id]
    p = vec(c.physics.position)
    v = vec(c.physics.linear_velocity)
    omega = vec(c.physics.angular_velocity)
    R = np.asarray(c.physics.rotation_mtx, dtype=float).reshape(3,3)
    return np.array([
        p[2]/300., v[0]/2300.,v[1]/2300.,v[2]/2300.,
        omega[0]/6.,omega[1]/6.,omega[2]/6.,
        R[2,0],R[2,1],R[2,2],
        np.dot(v, vec(forward))/2300.,
        float(c.on_ground), float(c.has_jumped),float(c.has_flipped),
        float(c.is_flipping),float(c.has_flip),
        float(c.air_time_since_jump), float(c.flip_time),
        tick/110.,
    ],dtype=np.float32)


class Simulator:
    def __init__(self):
        from rlgym.rocket_league.sim import RocketSimEngine
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
        self.engine=RocketSimEngine(rlbot_delay=False)
        self.teams=FixedTeamSizeMutator(blue_size=1,orange_size=1)
        self.kickoff=KickoffMutator()
        self.ours=None; self.them=None; self.forward=None; self.state=None

    def reset(self, seed, difficulty='near'):
        base = self.engine.create_base_state()
        self.teams.apply(base,{})
        self.kickoff.apply(base,{})
        is_orange = seed % 2 == 1
        self.ours=next(k for k,c in base.cars.items() if bool(c.is_orange)==is_orange)
        self.them=next(k for k in base.cars if k!=self.ours)
        self.forward=configure_wavedash(base,self.ours,self.them,seed,difficulty)
        self.state=self.engine.set_state(base,{})
        return self.state

    def step(self, action):
        action=np.asarray(action,dtype=np.float32)
        if action.shape != (8,): raise ValueError('expected eight controls')
        if not np.isfinite(action).all() or (np.abs(action)>1).any():
            raise ValueError('invalid controller values')
        self.state=self.engine.step({self.ours:action[None,:],
                                     self.them:ZERO[None,:]}, {})
        return self.state

    def close(self):
        self.engine.close()


def rollout(sim: Simulator, seed, params=None, *, policy=None, variant='forward',
            difficulty='near', max_ticks=100, frames=False):
    state=sim.reset(seed,difficulty)
    detector=WavedashDetector(state,sim.ours,sim.forward,max_ticks=max_ticks)
    samples=[]
    for t in range(max_ticks):
        x=feature_vector(state,sim.ours,sim.forward,t)
        action=(macro_control(params,t,variant) if policy is None
                else np.asarray(policy(x),dtype=np.float32))
        if frames: samples.append((x.tolist(),action.tolist()))
        state=sim.step(action)
        m=detector.observe(state,action)
        if detector.done: break
    return detector.metrics,samples


def output_metrics(m): return asdict(m)
