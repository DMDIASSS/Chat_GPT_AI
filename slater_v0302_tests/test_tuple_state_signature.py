"""Regression tests for RocketSim numeric tuple fields in kickoff signature."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import slater_fullmatch_eval_v0302 as fm


def make_state(wheels=(True, False, True, False)):
    phys = SimpleNamespace(
        position=np.array([0., -200., 17.]),
        linear_velocity=(0., 10., 0.),
        angular_velocity=np.array([0., 0., 0.]),
        rotation_mtx=((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)),
    )
    car_a = SimpleNamespace(physics=phys, boost_amount=33., on_ground=True,
                            wheels_with_contact=wheels,
                            is_demoed=False, has_jumped=False)
    car_b = SimpleNamespace(physics=phys, boost_amount=33., on_ground=True,
                            wheels_with_contact=wheels,
                            is_demoed=False, has_jumped=False)
    st = SimpleNamespace(
        tick_count=0,
        ball=SimpleNamespace(position=(0., 0., 93.),
                             linear_velocity=(0., 0., 0.),
                             angular_velocity=(0., 0., 0.)),
        cars={'blue-0': car_a, 'orange-0': car_b},
        boost_pad_timers=(0.0, 5.0, 0.0),
    )
    return SimpleNamespace(state=st)


def test_kickoff_signature_accepts_numeric_tuples_and_nested_rotation():
    env=make_state()
    first=fm.detailed_kickoff_signature(env)
    second=fm.detailed_kickoff_signature(env)
    assert first==second and isinstance(first,str) and len(first)==24
    assert fm.detailed_kickoff_signature(make_state((True, True, True, False))) != first


def test_kickoff_signature_rejects_bad_tuple():
    env=make_state((True, 'invalid'))
    with pytest.raises(TypeError, match=r'blue-0.wheels_with_contact'):
        fm.detailed_kickoff_signature(env)


def test_probe_imports_fixed_benchmark():
    probe=importlib.import_module('slater_sim_divergence_probe_v0302')
    assert probe.fm is fm


def test_comparison_still_enforces_strict_match_equality():
    a = {'seed': 99, 'side': 'blue', 'goals_for': 1,
         'goals_against': 0, 'goal_diff': 1, 'outcome': 1,
         'decisions': 120, 'touches': 2, 'opponent_touches': 4,
         'kickoffs': 2, 'first_kickoff_signature': 'same',
         'overtime': False, 'goal_events': []}
    b=dict(a)
    assert fm.match_equal(a,b)
    b['touches']=3
    assert not fm.match_equal(a,b)
