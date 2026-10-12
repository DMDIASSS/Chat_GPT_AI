"""Read-only fidelity CLI unit tests. No RocketSim installation required."""
import json
from pathlib import Path
import numpy as np
import pytest
from slater_research import fidelity_audit as audit


def test_choose_paths_sorted_and_limited(tmp_path):
    for n in ['b.npz','a.npz','c.npz']:
        (tmp_path / n).touch()
    assert [p.name for p in audit.choose_paths(tmp_path, 2, 'all')] == ['a.npz','b.npz']


def test_choose_paths_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match='No .npz'):
        audit.choose_paths(tmp_path, 5, 'all')
    with pytest.raises(ValueError, match='limit'):
        audit.choose_paths(tmp_path, 0, 'all')


def test_choose_paths_split_without_loading_clip(tmp_path):
    # SHA of all zeroes deterministically maps to the train split.
    np.savez(tmp_path/'x.npz', replay_sha=np.array('0'*64))
    assert len(audit.choose_paths(tmp_path, 1, 'train')) == 1
    assert len(audit.choose_paths(tmp_path, 1, 'validation')) == 0


def test_audit_record_error_does_not_halt_batch(tmp_path, monkeypatch):
    class DummyClip:
        replay_sha='0'*64
        ids=(1,2)
        snapshots=[object() for _ in range(7)]
        goal_step=6

    monkeypatch.setattr(audit.Clip, 'load', staticmethod(lambda _:DummyClip()))
    def maybe_fails(_clip, max_shot_position_error):
        if max_shot_position_error < 100:
            raise RuntimeError('sim error')
        return {'accepted':True, 'scored_as_reference':True, 'ball_error_uu_at_goal_frame':28.0}
    monkeypatch.setattr(audit,'counterfactual_goal_check', maybe_fails)
    good=audit.audit_one(tmp_path/'foo.npz', 250)
    bad=audit.audit_one(tmp_path/'foo.npz', 50)
    assert good['accepted'] is True and good['error'] is None
    assert bad['accepted'] is False and 'sim error' in bad['error']
    report=audit.make_report([tmp_path/'foo.npz'],250,progress=lambda *_args, **_kwargs: None)
    assert report['summary']['passed']==1
