import math
from dataclasses import dataclass
from types import SimpleNamespace
import numpy as np
from slater_research.geometry import (
    collision_ttc, ball_goal_threat, double_commit_pair, shadow_defense_quality)


def test_collision_direct():
    x=collision_ttc([0,0,20],[0,0,0],[1000,0,20],[-2300,0,0])
    assert 0.35 < x < .40


def test_collision_away():
    assert math.isinf(collision_ttc([0,0,0],[0,0,0],[2000,0,0],[2300,0,0]))


def test_on_target():
    t=ball_goal_threat([0,3500,400],[0,1800,0],defender_orange=True)
    assert t.danger and 0.8<t.time<1.0


def test_off_target():
    t=ball_goal_threat([1400,-2000,150],[0,1800,0],defender_orange=True)
    assert not t.danger


def test_shadow_position():
    ball=np.array([0,0,120]);net=np.array([0,-4400,50]);far=np.array([3000,-4400,50])
    assert shadow_defense_quality(net,ball,False)>shadow_defense_quality(far,ball,False)


def test_double_commit():
    def car(x,v):return SimpleNamespace(physics=SimpleNamespace(position=np.array([x,0,17.]),linear_velocity=np.array(v)))
    assert double_commit_pair(car(-120,[1000,0,0]),car(120,[-1000,0,0]),np.array([0,0,100]))
    assert not double_commit_pair(car(-120,[-1000,0,0]),car(120,[-1000,0,0]),np.array([0,0,100]))
