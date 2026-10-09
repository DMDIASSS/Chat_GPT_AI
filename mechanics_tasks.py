"""Measurable *proxies* for RL mechanics; not claims of completed human mechanics.

A successful speed-to-ball drill is not proof of a speedflip. A wall/ground
high-speed release is a pinch proxy; validate the actual animation manually.
"""
from __future__ import annotations
import numpy as np


def car_speed(car):
    return float(np.linalg.norm(np.asarray(car.physics.linear_velocity, dtype=float)))


def ball_speed(state):
    return float(np.linalg.norm(np.asarray(state.ball.linear_velocity, dtype=float)))


def distance(state, cid):
    return float(np.linalg.norm(np.asarray(state.cars[cid].physics.position) - np.asarray(state.ball.position)))


class MechanicsTracker:
    def __init__(self, stage: str, our_orange: bool, initial_state, our_id, max_steps: int):
        self.stage = stage
        self.orange = bool(our_orange)
        self.cid = our_id
        self.max_steps = max_steps
        self.t = 0
        self.success = False
        self.success_time = None
        self.events = 0
        self.touch_events = 0
        self.first_touch_owner = None
        self.air_streak = 0
        self.flip_low = False
        self.grounded_streak = 0
        self.initial_speed = car_speed(initial_state.cars[our_id])
        self.previous_car_speed = self.initial_speed
        self.previous_up = float(initial_state.cars[our_id].physics.rotation_mtx[2, 2])
        self.previous_ball_vel = np.array(initial_state.ball.linear_velocity, dtype=float)
        self.our_first_touch = False
        self.backboard = False
        self.touch_after_backboard = False
        self.last_touch_at = -10000
        self.start_distance = distance(initial_state, our_id)
        self.last_distance = self.start_distance
        self.start_boost = float(initial_state.cars[our_id].boost_amount)
        self.initial_ball_speed = ball_speed(initial_state)

    def update(self, state, our, opp, action, goal: bool, our_scored: bool):
        """Advance the tracker one decision (8 physics ticks), return (reward, done)."""
        self.t += 1
        c = state.cars[our]
        oppc = state.cars[opp]
        p = np.asarray(c.physics.position, dtype=float)
        bp = np.asarray(state.ball.position, dtype=float)
        bv = np.asarray(state.ball.linear_velocity, dtype=float)
        cv = np.asarray(c.physics.linear_velocity, dtype=float)
        ball_z = float(bp[2])
        speed = car_speed(c)
        ours_touch = int(getattr(c, 'ball_touches', 0)) > 0
        theirs_touch = int(getattr(oppc, 'ball_touches', 0)) > 0
        if self.first_touch_owner is None:
            if ours_touch:
                self.first_touch_owner = 'ours'
            elif theirs_touch:
                self.first_touch_owner = 'nexto'
        if ours_touch:
            self.touch_events += 1
        current_distance = float(np.linalg.norm(p - bp))
        # Single-step shaping and time penalty; capped to reduce spinning/oscillation exploits.
        progress = float(np.clip((self.last_distance-current_distance)/700., -.15, .15))
        r = .008 * progress - .0015
        self.last_distance = current_distance
        done = False
        qualified = False
        if self.stage == 'recovery':
            up_z = float(c.physics.rotation_mtx[2, 2])
            if c.on_ground and up_z > .70 and speed > 340:
                self.grounded_streak += 1
            else:
                self.grounded_streak = 0
            qualified = self.grounded_streak >= 3
            # Reward *improvement* in uprightness, not standing still upright forever.
            if p[2] < 250:
                r += .018 * max(0., up_z - self.previous_up)
            self.previous_up = up_z
        elif self.stage == 'wavedash':
            # Dodge activation near ground + controlled wheel landing with speed gain.
            if c.is_flipping and p[2] < 230 and not c.on_ground:
                self.flip_low = True
            if c.on_ground and float(c.physics.rotation_mtx[2, 2]) > .67 and speed > self.initial_speed+100:
                self.grounded_streak += 1
            else:
                self.grounded_streak = 0
            qualified = self.flip_low and self.grounded_streak >= 2
        elif self.stage == 'kickoff':
            # Time-to-first-touch target, NOT speedflip identification.
            if ours_touch and self.first_touch_owner == 'ours':
                qualified = self.t <= 38  # approx 2.53 seconds at 15 decisions/s
                r += 1.0 if qualified else .1
            if self.first_touch_owner == 'nexto' and not self.our_first_touch:
                r -= .1
                done = True
        elif self.stage == 'aerial_touch':
            qualified = ours_touch and ball_z > 330 and p[2] > 200
            if ours_touch and not qualified:
                r += .05
        elif self.stage == 'air_dribble':
            # Both airborne and close with matched velocities across >= 9 ticks (0.6s).
            rel_speed = float(np.linalg.norm(cv - bv))
            close = current_distance < 260 and p[2] > 280 and ball_z > 330 and rel_speed < 650
            self.air_streak = self.air_streak+1 if close else 0
            if close:
                r += .004
            qualified = self.air_streak >= 9 and self.touch_events >= 1
        elif self.stage == 'flip_reset':
            # Car started with no dodge; wheel contact on aerial ball should regain it.
            qualified = bool(c.has_flip) and not c.on_ground and ball_z > 300 and p[2] > 250
            if ours_touch and not qualified:
                r += .05
        elif self.stage == 'double_tap':
            attack = -1. if self.orange else 1.
            if ours_touch and not self.our_first_touch:
                self.our_first_touch = True
            board_y = attack * float(bp[1])
            bounced = (board_y > 4850 and ball_z > 230
                       and float(self.previous_ball_vel[1]) * attack > 150
                       and float(bv[1]) * attack < -150)
            if bounced and self.our_first_touch:
                self.backboard = True
            if self.backboard and ours_touch and self.last_touch_at < self.t-1:
                self.touch_after_backboard = True
            if ours_touch:
                self.last_touch_at = self.t
            qualified = self.touch_after_backboard and goal and our_scored
            if self.backboard:
                r += .002
        elif self.stage in ('ground_pinch', 'wall_pinch'):
            b_speed = ball_speed(state)
            pre_speed = float(np.linalg.norm(self.previous_ball_vel))
            wall = abs(bp[0]) > 3450
            ground = ball_z < 165
            attack = -1. if self.orange else 1.
            directed = bv[1]*attack > 350
            near_surface = ground if self.stage == 'ground_pinch' else wall
            qualified = (ours_touch and near_surface and b_speed > 1650
                         and b_speed-pre_speed > 350 and directed)
            if ours_touch and near_surface:
                r += .06
        elif self.stage == 'ceiling_touch':
            # Aerial touch after starting near ceiling; NOT full ceiling-shot completion.
            qualified = ours_touch and p[2] > 600 and ball_z > 550
        else:
            raise ValueError(self.stage)
        if goal:
            r += 1.0 if our_scored else -1.0
            done = True
        if qualified and not self.success:
            self.success = True
            self.success_time = self.t
            self.events += 1
            r += 4.0
            done = True
        if self.t >= self.max_steps:
            done = True
        self.previous_ball_vel = bv.copy()
        self.previous_car_speed = speed
        return float(r), bool(done)


class MechanicsMatch:
    def __init__(self, teacher, engine, stage, seed=123, orange=False, opponent='passive',
                 max_steps=120):
        from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
        self.teacher = teacher
        self.engine = engine
        self.stage = stage
        self.rng = np.random.default_rng(seed)
        self.our_orange = bool(orange)
        self.opponent_mode = opponent
        self.max_steps = int(max_steps)
        self.team = FixedTeamSizeMutator(blue_size=1, orange_size=1)
        self.kickoff = KickoffMutator()
        self.reset()

    def reset(self, orange=None):
        from mechanics_scenarios import configure
        if orange is not None:
            self.our_orange = bool(orange)
        base = self.engine.create_base_state()
        self.team.apply(base, {})
        self.kickoff.apply(base, {})
        ours = next(k for k,v in base.cars.items() if bool(v.is_orange)==self.our_orange)
        opp = next(k for k in base.cars if k != ours)
        configure(base, self.stage, ours, opp, self.rng)
        self.state = self.engine.set_state(base, {})
        self.ours, self.opponent = ours, opp
        self.previous = {}
        self.tracker = MechanicsTracker(self.stage, self.our_orange, self.state, ours, self.max_steps)
        return self.observe()

    def observe(self):
        views = self.teacher.observe(self.state, self.previous)
        return (next(v for v in views if v[0]==self.ours),
                next(v for v in views if v[0]==self.opponent))

    def step(self, our_action, their_action):
        from nexto_teacher import nexto_actions
        lookup = nexto_actions()
        us = lookup[int(our_action)]
        them = lookup[int(their_action)] if self.opponent_mode == 'nexto' else np.zeros(8, dtype=float)
        self.state = self.engine.step({self.ours:np.tile(us, (8,1)), self.opponent:np.tile(them, (8,1))}, {})
        self.previous = {self.ours:us, self.opponent:them}
        goal = bool(getattr(self.state, 'goal_scored', False))
        scored = ((float(self.state.ball.position[1]) > 0.) != self.our_orange)
        r, done = self.tracker.update(self.state, self.ours, self.opponent, us, goal, scored)
        return r, done, self.tracker.success
