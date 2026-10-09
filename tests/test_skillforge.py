import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skillforge_core import (WavedashDetector, macro_control,rotation,
                             search_parameters,feature_vector)
from skillforge_imitation import Specialist


def state(*, ground=False, jumped=True, flipped=False, flipping=False,
          boost=0, z=130, speed=500, vz=-280, omega=None, up=None):
    p=SimpleNamespace(position=np.array([0.,0.,z]),
       linear_velocity=np.array([0.,speed,vz]),
       angular_velocity=np.array(omega if omega is not None else [0.,0.,0.]),
       rotation_mtx=rotation([0.,1.,0.],up if up is not None else [0.,0.,1.]))
    c=SimpleNamespace(physics=p,on_ground=ground,has_jumped=jumped,
       has_flipped=flipped,is_flipping=flipping,is_holding_jump=False,
       has_double_jumped=False,air_time_since_jump=.2,flip_time=.08 if flipping else 0.,
       boost_amount=boost,has_flip=not flipped)
    return SimpleNamespace(cars={'us':c})


def attempt(*, dodge=True, landing=True, boost=False, spin=False, speed=760, start_flipped=False):
    s=state(flipped=start_flipped)
    d=WavedashDetector(s,'us',[0,1,0],max_ticks=16)
    if dodge:
        s=state(z=120,flipped=True,flipping=True,speed=500,vz=-270)
        d.observe(s,np.array([0,0,-1,0,0,1,0,0]))
    if landing:
        s=state(ground=True,flipped=dodge,flipping=True,
                z=20,speed=speed,vz=0,boost=0 if not boost else -1,
                omega=[800.,0,0] if spin else [0.,0,0])
        d.observe(s,np.array([0,0,1,0,0,0,int(boost),0]))
        for _ in range(5):
            s=state(ground=True,flipped=dodge,z=18,speed=speed,vz=0)
            d.observe(s,np.zeros(8))
    for _ in range(16):
        if d.done:break
        d.observe(s,np.zeros(8))
    return d.metrics


def test_verified_dodge_landing_without_full_flip():
    m=attempt()
    assert m.success,m
    assert m.dodge_detected and m.landed_during_dodge and m.wheels_down
    assert m.reason=='verified_wavedash'


def test_no_dodge_not_wavedash():
    m=attempt(dodge=False)
    assert not m.success
    assert not m.dodge_detected


def test_plain_air_flip_without_landing_not_wavedash():
    m=attempt(landing=False)
    assert not m.success


def test_ordinary_touchdown_without_speed_gain_not_wavedash():
    m=attempt(speed=550)
    assert not m.success
    assert m.dodge_detected
    assert m.speed_gain < 105


def test_boost_disqualifies():
    m=attempt(boost=True)
    assert not m.success
    assert not m.boost_free


def test_spinning_through_360_disqualifies():
    m=attempt(spin=True)
    assert not m.success
    assert not m.no_full_flip


def test_initially_flipped_cannot_be_reclassified():
    m=attempt(start_flipped=True)
    assert not m.success
    assert not m.valid_spawn


def test_wrong_orientation_rejected():
    s=state()
    d=WavedashDetector(s,'us',[0,1,0],max_ticks=10)
    s=state(z=100,flipped=True,flipping=True)
    d.observe(s,np.zeros(8))
    for i in range(9):
        s=state(ground=True,flipped=True,flipping=False,up=[0,0,-1],speed=780)
        d.observe(s,np.zeros(8))
    assert not d.metrics.success


def test_action_masks_and_airroll_only():
    pars={'delay':2,'hold':1,'cancel_delay':1,'cancel_ticks':9,'pre':0.5,'post':0.,'direction':-1.}
    for variant in ('forward','side','airroll_only'):
        for t in range(50):
            a=macro_control(pars,t,variant)
            assert a.shape == (8,)
            assert np.all(a[[0,1,6,7]]==0)
            assert np.max(np.abs(a)) <=1
            if variant=='airroll_only':
                assert not a[2] and not a[3] and not a[5]
    assert macro_control(pars,2)[5]==1
    assert macro_control(pars,3)[5]==0


def test_features_and_network():
    import torch
    s=state()
    x=feature_vector(s,'us',[0,1,0],0)
    assert x.shape==(19,) and np.isfinite(x).all()
    y=Specialist()(torch.from_numpy(x).unsqueeze(0))
    assert tuple(y.shape)==(1,4)


def test_macro_parameters_bounded():
    rng=np.random.default_rng(4)
    for _ in range(100):
        m=search_parameters(rng)
        assert 0 <= m['delay'] <=22
        assert 1 <= m['hold'] <=3
        assert 0 <= m['cancel_delay'] <=8
        assert 2 <= m['cancel_ticks'] <=24
        assert -.8<=m['pre']<=.8
