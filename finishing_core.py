"""Conservative, interpretable finishing-event heuristics for an isolated experiment.

All values are ROCKET LEAGUE Unreal units, not learned shot probabilities.
A predicted on-target ball is a rough gravity-only proxy; it does not account for
car saves, drag, bounces or ball radius. Never use this as a promotion gate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt
from typing import Any
import numpy as np

BACK_WALL_Y = 5120.0
GOAL_MOUTH_HALF_WIDTH = 780.0  # conservative inside posts, ball-center margin
GOAL_MOUTH_TOP = 560.0        # conservative inside crossbar, ball-center margin
GRAVITY = 650.0
DECISIONS_PER_SECOND = 15


def predict_direct_goal(position, velocity, attack_sign: float) -> bool:
    """Does a free, gravity-only ball path approximately enter the goal mouth?"""
    p = np.asarray(position, dtype=float)
    v = np.asarray(velocity, dtype=float)
    forward = float(attack_sign * v[1])
    remain = BACK_WALL_Y - float(attack_sign * p[1])
    if forward < 550.0 or remain <= 80.0:
        return False
    t = remain / forward
    if t <= 0.03 or t > 2.4:
        return False
    x = float(p[0] + t * v[0])
    z = float(p[2] + t * v[2] - 0.5 * GRAVITY * t * t)
    return abs(x) < GOAL_MOUTH_HALF_WIDTH and 94.0 <= z <= GOAL_MOUTH_TOP


def opponent_has_lane(state: Any, ours: Any, opponent: Any) -> bool:
    """Simple obstruction proxy: opponent sits between ball and attacking goal."""
    ball = np.asarray(state.ball.position, dtype=float)
    other = np.asarray(state.cars[opponent].physics.position, dtype=float)
    attack = -1.0 if state.cars[ours].is_orange else 1.0
    forward = (other[1] - ball[1]) * attack
    return bool(100.0 < forward < 1400.0 and abs(other[0] - ball[0]) < 700.0)


@dataclass
class FinishingTracker:
    """Single-episode event tracker; add tiny REWARD only on meaningful events.

    A mere ball touch, direction toward net or backboard bounce earns no bonus.
    Event reward is intentionally tiny relative to the +/- 10 goal reward.
    """
    our_orange: bool
    last_touch_tick: int = -999
    last_direct_tick: int = -999
    last_forward_release_tick: int = -999
    last_board_tick: int = -999
    board_followup_paid: bool = False
    tick: int = 0
    previous_ball_position: np.ndarray | None = None
    previous_ball_velocity: np.ndarray | None = None
    counts: dict[str, int] = field(default_factory=lambda: {
        'ours_touch': 0, 'direct_on_target_proxy': 0,
        'forward_release_proxy': 0, 'off_target_forward_release_proxy': 0,
        'blocked_lane_on_target': 0, 'backboard_bounce_proxy': 0,
        'followup_on_target_proxy': 0, 'flick_on_target_proxy': 0,
        'goals_ours': 0, 'goals_against': 0,
    })

    def begin(self, state: Any) -> None:
        self.previous_ball_position = np.asarray(state.ball.position, dtype=float).copy()
        self.previous_ball_velocity = np.asarray(state.ball.linear_velocity, dtype=float).copy()

    def step(self, state: Any, ours: Any, opponent: Any, *, goal: bool = False,
             winner: str = 'draw') -> tuple[float, dict[str, bool]]:
        self.tick += 1
        if self.previous_ball_position is None:
            self.begin(state)
        p = np.asarray(state.ball.position, dtype=float)
        v = np.asarray(state.ball.linear_velocity, dtype=float)
        prev_p, prev_v = self.previous_ball_position, self.previous_ball_velocity
        attack = -1.0 if self.our_orange else 1.0
        car = state.cars[ours]
        touched = bool(getattr(car, 'ball_touches', 0))
        on_target = predict_direct_goal(p, v, attack)
        events = {'on_target': False, 'backboard': False, 'followup': False, 'flick': False}
        bonus = 0.0

        # Detect goal-side wall contact, avoiding a false positive on goals.
        # It is a proxy: state snapshots are 8 physics ticks apart.
        board = (not goal and self.tick - self.last_touch_tick <= 55
                 and abs(float(p[0])) < 2000 and float(p[2]) > 620
                 and attack * float(prev_v[1]) > 350
                 and attack * float(v[1]) < -180
                 and max(attack * float(prev_p[1]), attack * float(p[1])) > 4750)
        if board and self.tick - self.last_board_tick > 20:
            self.last_board_tick = self.tick
            self.board_followup_paid = False
            self.counts['backboard_bounce_proxy'] += 1
            events['backboard'] = True

        if touched:
            self.counts['ours_touch'] += 1
            # Diagnostic only: count significant offensive releases; do not
            # penalize aim or demand a direct shot when the lane is blocked.
            if (attack * float(v[1]) > 650 and attack * float(p[1]) > 450
                    and self.tick - self.last_forward_release_tick >= 24):
                self.last_forward_release_tick = self.tick
                self.counts['forward_release_proxy'] += 1
                if not on_target:
                    self.counts['off_target_forward_release_proxy'] += 1
            # Reward accurate releases only (not generic hits, flicking or bounces).
            if on_target and self.tick - self.last_direct_tick >= 24:
                self.last_direct_tick = self.tick
                events['on_target'] = True
                self.counts['direct_on_target_proxy'] += 1
                blocked = opponent_has_lane(state, ours, opponent)
                if blocked:
                    self.counts['blocked_lane_on_target'] += 1
                # A guarded lane reduces, rather than amplifies, direct shot reward.
                bonus += 0.025 if blocked else 0.065
                if bool(getattr(car, 'is_flipping', False)) and float(p[2]) >= 190:
                    events['flick'] = True
                    self.counts['flick_on_target_proxy'] += 1
                    bonus += 0.025  # Proxy only; NOT confirmed as a human flick.
            # Backboard reward requires a *second* touch that redirects on goal.
            if (self.last_board_tick >= 0 and not self.board_followup_paid
                    and 1 <= self.tick - self.last_board_tick <= 42 and on_target):
                self.board_followup_paid = True
                events['followup'] = True
                self.counts['followup_on_target_proxy'] += 1
                bonus += 0.12
            self.last_touch_tick = self.tick

        if goal:
            if winner == 'ours':
                self.counts['goals_ours'] += 1
            elif winner == 'nexto':
                self.counts['goals_against'] += 1
        self.previous_ball_position = p.copy()
        self.previous_ball_velocity = v.copy()
        return min(bonus, 0.21), events
