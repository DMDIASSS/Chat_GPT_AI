"""Small, conservative training rewards for boost efficiency and defensive recovery.
Not a substitute for goal difference. No hard control overrides; the PPO policy
can still spend boost / overcommit if it expects a valuable play.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


def goal_threat(state, our_orange):
    """Approximate 0..1 own-goal danger over <= 2.5 seconds.

    Rocket League has walls, hits, gravity and saves, so this is a diagnostic
    proxy, not a precise scoring probability.
    """
    p = np.asarray(state.ball.position, dtype=float)
    v = np.asarray(state.ball.linear_velocity, dtype=float)
    own_y = 5120.0 if our_orange else -5120.0
    toward_goal = 1 if our_orange else -1
    advance = toward_goal * v[1]
    remaining = toward_goal * (own_y - p[1])
    if remaining <= 0 or advance < 350:
        return 0.0
    eta = remaining / advance
    if eta > 2.5:
        return 0.0
    x_goal = p[0] + v[0] * eta
    # Simplified ball floor collision: treat descending ground-level shots as
    # threatening instead of falsely predicting the ball passing underground.
    z_goal = max(93.0, p[2] + v[2] * eta - .5 * 650 * eta**2)
    if abs(x_goal) > 960 or z_goal > 710:
        return 0.0
    return float(np.clip(1.0 - 0.20 * eta, 0, 1))


def boost_waste(pre_boost, post_boost, pre_speed, ball_distance, danger):
    """Penalize only conspicuously pointless sustained boost usage."""
    spent = pre_boost - post_boost
    return bool(spent >= 0.15 and pre_speed > 2180 and ball_distance > 1900 and danger < 0.1)


@dataclass
class BalanceTracker:
    orange: bool
    last_pickup: int = -1000
    last_save: int = -1000
    tick: int = 0
    counters: dict[str, int] = field(default_factory=lambda: {
        'boost_efficient_pickups':0, 'boost_waste_flags':0,
        'urgent_saves':0, 'goal_threat_steps':0,
        'dangerous_own_touches':0,
    })

    def step(self, *, before, after, ours, opponent, our_touch=False, goal=False):
        self.tick += 1
        b = before.cars[ours]
        a = after.cars[ours]
        old_boost = float(b.boost_amount)
        new_boost = float(a.boost_amount)
        old_p = np.asarray(b.physics.position,dtype=float)
        ball_p = np.asarray(before.ball.position,dtype=float)
        dist = float(np.linalg.norm(ball_p-old_p))
        speed = float(np.linalg.norm(np.asarray(b.physics.linear_velocity,dtype=float)))
        old_danger = goal_threat(before,self.orange)
        new_danger = goal_threat(after,self.orange)
        bonus = 0.0
        if old_danger > 0.5:
            self.counters['goal_threat_steps'] += 1
        if boost_waste(old_boost,new_boost,speed,dist,old_danger):
            self.counters['boost_waste_flags'] += 1
            bonus -= 0.004
        # Do not pay repeatedly for tiny pad fluctuations or pickups while in danger.
        if (new_boost-old_boost >= 9 and old_boost < 65 and old_danger < 0.25
                and self.tick-self.last_pickup >= 30):
            self.last_pickup = self.tick
            self.counters['boost_efficient_pickups'] += 1
            bonus += 0.012
        # A touch which immediately creates a plausible own-goal shot is bad,
        # without discouraging normal forward challenges or risky opponent-half play.
        if our_touch and old_danger < .15 and new_danger > .65 and not goal:
            self.counters['dangerous_own_touches'] += 1
            bonus -= 0.018
        # A genuinely threatening ball redirected away from goal by OUR contact.
        if (not goal and our_touch and old_danger > .55 and new_danger < old_danger-.35
                and self.tick-self.last_save >= 20):
            self.last_save = self.tick
            self.counters['urgent_saves'] += 1
            bonus += 0.055
        return float(np.clip(bonus,-0.022,0.07))
