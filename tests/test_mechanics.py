import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mechanics_scenarios import STAGES, basis, configure
from mechanics_tasks import MechanicsTracker

class Physics:
    def __init__(self,pos=(0,0,25),vel=(0,0,0)):
        self.position=np.array(pos,dtype=float)
        self.linear_velocity=np.array(vel,dtype=float)
        self.angular_velocity=np.zeros(3)
        self.rotation_mtx=np.eye(3)

class Car:
    def __init__(self,orange=False):
        self.is_orange=orange
        self.physics=Physics()
        self.boost_amount=50.
        self.on_ground=True
        self.ball_touches=0
        self.has_flipped=False
        self.has_double_jumped=False
        self.has_jumped=False
        self.is_holding_jump=False
        self.is_jumping=False
        self.air_time_since_jump=0.
        self.flip_time=0.
    @property
    def has_flip(self):
        return not self.has_flipped and not self.has_double_jumped and self.air_time_since_jump < 1.25
    @property
    def is_flipping(self):
        return self.has_flipped and self.flip_time < .6

class State:
    def __init__(self):
        self.cars={1:Car(),2:Car(True)}
        self.ball=Physics(pos=(0,0,93))
        self.goal_scored=False

@pytest.mark.parametrize('stage', STAGES)
def test_valid_reset_geometry(stage):
    state=State()
    configure(state,stage,1,2,np.random.default_rng(11))
    for car in state.cars.values():
        m=car.physics.rotation_mtx
        assert np.allclose(m.T @ m,np.eye(3), atol=1e-5)
        assert np.linalg.det(m)>0.99
        assert np.isfinite(car.physics.position).all()
    assert 90 <= state.ball.position[2] <= 1950
    assert np.linalg.norm(state.ball.position) > 0
    if stage!='kickoff':
        assert np.linalg.norm(state.ball.position-state.cars[1].physics.position)>95


def test_recovery_success_requires_consecutive_upright_landing():
    s=State();c=s.cars[1]
    c.physics.position=np.array([0,0,350.]); c.physics.linear_velocity=np.array([600,0,0]); c.on_ground=False
    tracker=MechanicsTracker('recovery',False,s,1,10)
    for i in range(2):
        c.on_ground=True
        _,done=tracker.update(s,1,2,np.zeros(8),False,False)
        assert not done
    _,done=tracker.update(s,1,2,np.zeros(8),False,False)
    assert done and tracker.success


def test_flip_reset_requires_regained_flip_while_airborne():
    s=State();c=s.cars[1]; c.physics.position=np.array([0,0,600.]);c.has_flipped=True;c.on_ground=False
    s.ball.position=np.array([0,130,550.])
    tracker=MechanicsTracker('flip_reset',False,s,1,5)
    _,done=tracker.update(s,1,2,np.zeros(8),False,False)
    assert not done and not tracker.success
    c.has_flipped=False
    _,done=tracker.update(s,1,2,np.zeros(8),False,False)
    assert done and tracker.success


def test_aerial_touch_needs_height():
    s=State();c=s.cars[1];c.ball_touches=1
    tr=MechanicsTracker('aerial_touch',False,s,1,10)
    _,done=tr.update(s,1,2,np.zeros(8),False,False)
    assert not done
    c.physics.position[2]=500;s.ball.position[2]=800
    _,done=tr.update(s,1,2,np.zeros(8),False,False)
    assert tr.success and done


def test_pinch_without_surface_is_not_success():
    s=State(); c=s.cars[1];c.ball_touches=1
    tr=MechanicsTracker('wall_pinch',False,s,1,10)
    s.ball.linear_velocity=np.array([0,2200,0.]);s.ball.position=np.array([0.,0.,500.])
    _,done=tr.update(s,1,2,np.zeros(8),False,False)
    assert not tr.success and not done


def test_time_limit():
    s=State(); tr=MechanicsTracker('air_dribble',False,s,1,2)
    assert not tr.update(s,1,2,np.zeros(8),False,False)[1]
    assert tr.update(s,1,2,np.zeros(8),False,False)[1]


def test_orthonormal_oblique_basis():
    m=basis([1.,2.,3.],[.15,0.,1.])
    assert np.allclose(m.T @ m,np.eye(3),atol=1e-7)
    assert np.linalg.det(m)>0.99
    assert np.allclose(m[:,0],np.array([1.,2.,3.])/np.linalg.norm([1.,2.,3.]))
