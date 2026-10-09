import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sf2_core import (set_scenario, Script, HeightTriggeredDodge, Detector,
                      orientation, ZERO, metrics_json)
from sf2_watch import run, parse, load_script
from sf2_search import search, parse as search_parse


def car(z=130, speed=600, ground=False, flip=False, flipping=False, vz=-390):
    return SimpleNamespace(
        physics=SimpleNamespace(position=np.array([0.,-1350.,float(z)]),
          linear_velocity=np.array([0.,float(speed),float(vz)]),
          rotation_mtx=orientation([0,1,0.2]),angular_velocity=np.zeros(3)),
        on_ground=ground,has_jumped=True,has_flipped=flip,is_flipping=flipping,
        is_holding_jump=False,is_jumping=False,has_double_jumped=False,
        air_time_since_jump=0.2,flip_time=0.,flip_torque=np.zeros(3),
        is_autoflipping=False,autoflip_timer=0.,autoflip_direction=0.,
        boost_amount=0.,wheels_with_contact=(ground,)*4)


def state(c=None):
    return SimpleNamespace(cars={'us':c or car()}, ball=SimpleNamespace(
        position=np.array([0.,0.,93.]),linear_velocity=np.zeros(3),
        angular_velocity=np.zeros(3)))


def test_ball_ahead_and_single_car():
    s=state()
    direction=set_scenario(s,'us',701,nose=.22)
    assert len(s.cars)==1
    assert np.allclose(direction,[0,1,0])
    assert s.ball.position[1] > s.cars['us'].physics.position[1]+1000
    assert abs(s.ball.position[0]-s.cars['us'].physics.position[0]) < 1e-5
    assert s.cars['us'].physics.rotation_mtx[1,0] > .95
    assert s.cars['us'].boost_amount == 0


def test_trigger_not_fixed_ticks_and_cancel_direction():
    s=Script(threshold=40., nose=.16, cancel_ticks=10)
    ctrl=HeightTriggeredDodge(s)
    for z in (120,90,55,42):
        a=ctrl.action(car(z=z))
        assert a[5]==0
    a=ctrl.action(car(z=39))
    assert a[5]==1 and a[2]==-1
    a=ctrl.action(car(z=35,flip=True))
    assert a[5]==0 and a[2]==1
    assert not (a[[0,1,6,7]]).any()
    for i in range(12):
        a=ctrl.action(car(z=28, ground=True, flip=True))
    assert a[5]==0 and a[2]==0


def feed(det, c, action=None):
    return det.observe(state(c), ZERO if action is None else action)


def test_dodge_and_ground_contact_detected_even_if_flags_reset_on_landing():
    d=Detector(state(), 'us', max_ticks=20)
    feed(d,car(z=42, speed=600))
    a=ZERO.copy();a[2]=-1.;a[5]=1
    feed(d,car(z=38,speed=820, flip=True,flipping=True),a)
    assert d.metrics.dodge and d.metrics.impulse_gain>=100
    # Ground collision resets both flip flags in RocketSim; previous frame is the evidence.
    feed(d,car(z=19,speed=810,ground=True,flip=False,flipping=False,vz=0))
    assert d.metrics.landing_during_dodge
    for _ in range(4):
        feed(d,car(z=18,speed=810,ground=True,vz=0))
    assert d.metrics.success
    assert d.metrics.contact_wheels == 4


def test_no_plain_landing_no_success():
    d=Detector(state(),'us',max_ticks=10)
    for i in range(10):
        m=feed(d,car(z=18,ground=True,vz=0,speed=620))
    assert not m.success and m.reason == 'no_dodge_before_landing'


def test_no_long_airborne_flip():
    d=Detector(state(),'us',max_ticks=18)
    feed(d,car(z=70,flip=True,flipping=True,speed=800))
    for _ in range(12):
        feed(d,car(z=40,flip=True,flipping=False,speed=800))
    feed(d,car(z=18,flip=False,ground=True,speed=800,vz=0))
    for _ in range(4):
        feed(d,car(z=18,ground=True,speed=800,vz=0))
    assert not d.metrics.landing_during_dodge
    assert not d.metrics.success


def test_wrong_controls_fail():
    d=Detector(state(),'us',max_ticks=12)
    a=ZERO.copy();a[6]=1
    feed(d,car(z=38,flip=True,flipping=True,speed=780),a)
    feed(d,car(z=18,ground=True,speed=780,vz=0))
    for _ in range(4): feed(d,car(z=18,ground=True,speed=780,vz=0))
    assert not d.metrics.success
    assert not d.metrics.used_no_driving_controls


class FakeSim:
    def __init__(self):
        self.ours='us';self.state=None;self.calls=0;self.closed=False
    def reset(self,seed,nose=0.16):
        self.calls=0
        self.state=state()
        set_scenario(self.state,'us',seed,nose)
        return self.state
    def step(self,a):
        self.calls+=1
        c=self.state.cars['us']
        c.physics.position[2] -= 9
        if a[5]>0:
            c.has_flipped=True;c.is_flipping=True
            c.physics.linear_velocity[1]+=180
        if self.calls>=13:
            c.on_ground=True
            c.has_flipped=False;c.is_flipping=False
            c.physics.position[2]=19
            c.physics.linear_velocity[2]=0
            c.wheels_with_contact=(True,True,True,True)
        return self.state
    def close(self):self.closed=True


class FakeRenderer:
    def __init__(self,tick_rate): self.calls=0;self.closed=False
    def render(self,state,shared): self.calls+=1
    def close(self):self.closed=True


def test_mock_viewer(tmp_path):
    trace=tmp_path/'trace.csv'
    args=parse(['--mode','timed','--repeat','2','--seeds','2','--max-ticks','18',
                '--trace',str(trace),'--spawn-pause','0','--pause','0',
                '--speed','4'])
    sims=[];renderers=[]
    def sf():
        obj=FakeSim(); sims.append(obj);return obj
    def rf(tick_rate):
        obj=FakeRenderer(tick_rate);renderers.append(obj);return obj
    run(args,simulator_factory=sf,renderer_factory=rf,sleep=lambda _:None)
    assert sims[0].closed and renderers[0].closed
    text=trace.read_text()
    assert 'car_y' in text and 'dodge_detected' in text
    assert len(text.splitlines()) > 15


def test_load_saved_calibration(tmp_path):
    filename=tmp_path/'calibration.json'
    data={'candidate': vars(Script(threshold=49,nose=.12))}
    filename.write_text(json.dumps(data))
    assert load_script('best',filename).threshold==49
    with pytest.raises(FileNotFoundError): load_script('best',tmp_path/'missing.json')


def test_search_mock_does_not_touch_models(tmp_path):
    out=tmp_path/'report.json'
    args=search_parse(['--train-seeds','1','--test-seeds','1','--max-ticks','15','--out',str(out)])
    res=search(args,simulator_factory=FakeSim)
    assert out.exists()
    assert not res['verified_for_imitation']
    assert len(res['all_training_results']) == 7*4*3
    with pytest.raises(FileExistsError): search(args,simulator_factory=FakeSim)
