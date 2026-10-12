"""Physics-derived, engine-independent diagnostics. Units: uu and seconds."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

GRAVITY = 650.0  # soccar approximate; prefer state.config.gravity * -650 for nonstandard modes
GOAL_Y = 5120.0
GOAL_HALF_WIDTH = 892.0
CROSSBAR_Z = 642.0
BALL_RADIUS = 92.75
SUPERSONIC_SPEED = 2200.0


def norm(v): return float(np.linalg.norm(np.asarray(v, dtype=np.float64)))

def unit(v):
    a = np.asarray(v, dtype=np.float64)
    return a / max(norm(a), 1e-9)


def clamp(x, lo=0.0, hi=1.0): return float(np.clip(x, lo, hi))


def collision_ttc(p_self, v_self, p_other, v_other, radius=160.0, horizon=0.8):
    """Swept 3D sphere approximation (not a RocketSim geometry raycast).

    Returns first relative-contact time or +inf. For car-car demos refine with
    oriented boxes/actual RocketSim contacts and visibility checks.
    """
    p = np.asarray(p_other, float) - np.asarray(p_self, float)
    v = np.asarray(v_other, float) - np.asarray(v_self, float)
    a = float(v @ v)
    c = float(p @ p) - radius * radius
    if c <= 0: return 0.0
    if a < 1e-8: return math.inf
    b = 2 * float(p @ v)
    d = b*b - 4*a*c
    if d < 0: return math.inf
    t = (-b - math.sqrt(d)) / (2*a)
    return t if 0 <= t <= horizon else math.inf


@dataclass(frozen=True)
class GoalThreat:
    danger: bool
    time: float
    x: float
    z: float
    margin: float


def ball_goal_threat(position, velocity, defender_orange: bool, horizon=2.5,
                     uncertainty=0.0, gravity=GRAVITY) -> GoalThreat:
    """Ballistic short-horizon goal-plane intersection, ignoring wall bounces.

    Treat as a *screening heuristic*, not a real goal predictor. Uncertainty
    enlarges the relevant shot width for delayed redirects and flip resets.
    """
    p = np.asarray(position, float)
    v = np.asarray(velocity, float)
    target_y = GOAL_Y if defender_orange else -GOAL_Y
    if abs(v[1]) < 1e-6: return GoalThreat(False, math.inf, math.nan, math.nan, -math.inf)
    t = (target_y - p[1]) / v[1]
    if not 0 < t <= horizon: return GoalThreat(False, t, math.nan, math.nan, -math.inf)
    x = float(p[0] + v[0]*t)
    z = float(p[2] + v[2]*t - 0.5*gravity*t*t)
    limit_x = GOAL_HALF_WIDTH + BALL_RADIUS + uncertainty
    margin = min(limit_x - abs(x), CROSSBAR_Z + BALL_RADIUS + uncertainty - z, z + BALL_RADIUS + uncertainty)
    return GoalThreat(margin >= 0, float(t), x, z, float(margin))


def flip_reset_event(previous_car, car, ball_position, proximity=200.0):
    """Candidate reset: airborne, spent flip -> regained flip near ball.

    Requires a simultaneous ball touch; wheel-on-ball verification should use
    RocketSim contact geometry in a final detector.
    """
    return (not bool(previous_car.has_flip) and bool(car.has_flip)
            and not bool(car.on_ground) and not bool(previous_car.on_ground)
            and int(car.ball_touches) > 0
            and norm(car.physics.position - np.asarray(ball_position)) < proximity)


def double_commit_pair(a, b, ball, *, distance=450.0, minimum_closing=400.0):
    pa = np.asarray(a.physics.position, float)
    pb = np.asarray(b.physics.position, float)
    bp = np.asarray(ball, float)
    da, db = norm(bp-pa), norm(bp-pb)
    if da >= distance or db >= distance: return False
    va = float(np.dot(a.physics.linear_velocity, unit(bp-pa)))
    vb = float(np.dot(b.physics.linear_velocity, unit(bp-pb)))
    return va > minimum_closing and vb > minimum_closing


def shadow_defense_quality(car_pos, ball_pos, defender_orange, x_width=1300.0):
    """Ball-goal line coverage, not a complete game-theoretic shadow policy."""
    p, b = np.asarray(car_pos, float), np.asarray(ball_pos, float)
    net = np.array([0., GOAL_Y if defender_orange else -GOAL_Y, 0.])
    seg = net - b
    u = clamp(float(np.dot(p-b,seg))/max(float(seg@seg), 1), 0, 1)
    intercept = b+u*seg
    lateral = norm((p-intercept)[:2])
    return math.exp(-0.5*(lateral/x_width)**2)
