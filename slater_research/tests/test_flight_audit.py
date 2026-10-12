"""Unit tests for short-horizon fidelity diagnostic; no installed RocketSim required."""
import json
from pathlib import Path
import numpy as np
import pytest
from slater_research import flight_audit as diag


def test_choose_diverse_source_replays(tmp_path):
    a, b, c = '0'*64, '1'*64, '2'*64
    for name, sha in [('a1.npz',a),('a2.npz',a),('b1.npz',b),('b2.npz',b),('c1.npz',c)]:
        np.savez(tmp_path/name, replay_sha=np.array(sha))
    paths = diag.choose_diverse_clips(tmp_path, 4)
    assert [p.name for p in paths] == ['a1.npz','b1.npz','c1.npz','a2.npz']
    assert [p.name for p in diag.choose_diverse_clips(tmp_path, 2)] == ['a1.npz','b1.npz']


def test_empty_and_limit_rejection(tmp_path):
    with pytest.raises(ValueError, match='positive'):
        diag.choose_diverse_clips(tmp_path, 0)
    with pytest.raises(ValueError, match='No matching'):
        diag.choose_diverse_clips(tmp_path, 5)


def test_outcome_does_not_pass_early_score():
    x = diag.review_goal_outcome(reference_goal_step=10, stopped_step=7,
            actual_goal_step=7, correct_goal=True, stopped_error=40,
            goal_frame_error=None, max_error=250)
    assert x['scored_as_reference']
    assert x['early_goal_unverifiable']
    assert not x['accepted']
    assert x['ball_error_uu_at_reference_goal'] is None


def test_outcome_not_pass_no_goal_even_when_error_zero():
    x = diag.review_goal_outcome(reference_goal_step=10, stopped_step=10,
            actual_goal_step=None, correct_goal=False, stopped_error=0,
            goal_frame_error=0, max_error=250)
    assert not x['accepted']


def test_outcome_pass_goal_within_tolerance():
    x = diag.review_goal_outcome(reference_goal_step=10, stopped_step=10,
            actual_goal_step=10, correct_goal=True, stopped_error=12,
            goal_frame_error=12, max_error=250)
    assert x['accepted']


def test_outcome_reject_nonfinite_distance():
    x = diag.review_goal_outcome(reference_goal_step=10, stopped_step=10,
            actual_goal_step=10, correct_goal=True, stopped_error=float('inf'),
            goal_frame_error=float('inf'), max_error=250)
    assert not x['accepted']


def test_report_with_simulation_mock(tmp_path, monkeypatch):
    np.savez(tmp_path/'a.npz', replay_sha=np.array('0'*64))
    class DummyClip:
        replay_sha='0'*64
        ids=(1,2)
        goal_step=3
        snapshots=[None for _ in range(4)]
    monkeypatch.setattr(diag.Clip,'load',staticmethod(lambda _:DummyClip()))
    monkeypatch.setattr(diag,'run_window',lambda *args,**kwargs: {'accepted':True,'error':None})
    report=diag.run_report(tmp_path,1,[.5],250,progress=lambda *a,**kw:None)
    assert report['summary']=={'replays':1,'clips':1,'window_runs':2,'accepted':2,'early_unverifiable':0,'errors':0}
