"""Experimental RLBot v4 Cycle9 Fusion decision and second-man coverage logic.

No trained weights are changed.  This is a heuristic supervisory layer, not learned
teamplay.  Deliberately has no RLBot import so geometry can be unit tested.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


def clamp(x, low, high):
    return max(low, min(high, float(x)))


def xy(value):
    return np.asarray(value, dtype=float).reshape(-1)[:2]


def uid(player):
    return int(player.car_id)


def approach_time(car, ball):
    pos = xy(car.car_data.position)
    speed = xy(car.car_data.linear_velocity)
    displacement = xy(ball) - pos
    dist = float(np.linalg.norm(displacement))
    toward = float(np.dot(speed, displacement) / max(dist, 1.0))
    # Physically approximate time, not a precise ball interception prediction.
    effective_speed = clamp(900 + .48*toward, 530, 1850)
    eta = dist / effective_speed
    if not car.on_ground:
        eta += .28
    return eta


def first_man(you, teammates, ball, kickoff=False, team=0):
    players = [you] + list(teammates)
    if len(players) == 1:
        return uid(you)
    if kickoff:
        # Equal-distance kickoff: left goes, in team's own forward-facing view.
        def key(p):
            d = float(np.linalg.norm(xy(p.car_data.position)))
            return (round(d / 15.0), p.car_data.position[0] if team == 0 else -p.car_data.position[0], uid(p))
    else:
        # Stable deterministic tie-breaking so two separately-running bots
        # calculate the same first man from a shared game packet.
        def key(p):
            t = approach_time(p, ball)
            attack_sign = 1 if team == 0 else -1
            # Small penalty when already beyond the play: coverage may be poor.
            behind_ball = attack_sign * (p.car_data.position[1] - ball[1]) > 450
            return (round((t + (.20 if behind_ball else 0)) / .09), uid(p))
    return uid(min(players, key=key))


def defensive_danger(ball, ball_vel, team):
    sign = 1 if team == 0 else -1
    forward_y = sign * float(ball[1])
    toward_ours = sign * float(ball_vel[1])
    return forward_y < -3800 or (forward_y < -1800 and toward_ours < -260)


def support_target(ball, teammate, team):
    sign = 1 if team == 0 else -1
    attack_y = sign * float(ball[1])
    # Always leave the goal side covered and stay separated from first man.
    backup_y = clamp(attack_y - 1350, -4440, 3350)
    x = clamp(float(ball[0]) * .36, -2050, 2050)
    mate_x = float(teammate.car_data.position[0])
    mate_y = float(teammate.car_data.position[1])
    if math.hypot(x - mate_x, sign*backup_y - mate_y) < 720:
        x = clamp(x + (-850 if mate_x >= x else 850), -2400, 2400)
    return np.array([x, sign * backup_y], dtype=float)


def drive_toward(player, target, teammates=()):
    """Conservative ground support controller, returns Nexto's 8 controls."""
    pos = xy(player.car_data.position)
    v = xy(player.car_data.linear_velocity)
    displacement = xy(target) - pos
    dist = float(np.linalg.norm(displacement))
    orientation = np.asarray(player.car_data.rotation_mtx(), dtype=float)
    forward = orientation[:2, 0]
    forward_norm = max(float(np.linalg.norm(forward)), 1.e-6)
    forward = forward / forward_norm
    target_dir = displacement / max(dist, 1.0)
    error = math.atan2(float(forward[0]*target_dir[1] - forward[1]*target_dir[0]),float(np.dot(forward,target_dir)))
    speed = float(np.linalg.norm(v))
    steer = clamp(2.15*error,-1.,1.)
    throttle = 1. if dist > 570 else (0.0 if speed < 220 else -1.)
    if abs(error) > 2.2 and speed > 250:
        throttle = -0.35
    # Brake rather than boost into a close teammate.
    for mate in teammates:
        gap = xy(mate.car_data.position) - pos
        ahead = float(np.dot(gap,forward))
        if 0 < ahead < 470 and float(np.linalg.norm(gap)) < 520:
            throttle = -1.0
            break
    boost = float(dist > 2100 and abs(error) < .18 and speed < 1350 and throttle > .5)
    handbrake = float(abs(error) > 1.0 and speed > 850)
    # throttle / steer / pitch / yaw / roll / jump / boost / handbrake
    return np.array([throttle,steer,0.,steer,0.,0.,boost,handbrake],dtype=float)


@dataclass
class FusionDecision:
    role: str
    policy: str
    target: object = None
    danger: bool = False
    owner_id: int = -1


def decide(you, teammates, opponents, ball, vel, team, kickoff=False):
    ball = np.asarray(ball,dtype=float)
    vel = np.asarray(vel,dtype=float)
    mates = list(teammates)
    owner = first_man(you,mates,ball,kickoff=kickoff,team=team)
    danger = defensive_danger(ball,vel,team)
    if owner != uid(you):
        teammate = next(p for p in mates if uid(p)==owner)
        return FusionDecision('second','support',support_target(ball,teammate,team),danger,owner)
    forward = 1 if team == 0 else -1
    ball_attack_y = forward * float(ball[1])
    my_distance = float(np.linalg.norm(xy(you.car_data.position)-xy(ball)))
    enemy_distance = min((float(np.linalg.norm(xy(e.car_data.position)-xy(ball))) for e in opponents), default=9999.)
    # Use champion for forward finishing only when reasonably close to a shooting lane.
    can_finish = (ball_attack_y > 650 and abs(ball[0]) < 1800 and
                  my_distance < 1650 and enemy_distance > 460 and not danger)
    if danger:
        policy='wavedash'
    elif can_finish:
        policy='champion'
    else:
        policy='cycle9'
    return FusionDecision('first',policy,None,danger,owner)
