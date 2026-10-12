import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import slater_v038a_gate as m


def _physics(x=0):
    return NS(position=np.array([x,0,93.],dtype=np.float32),
              linear_velocity=np.array([0.,0.,1.]),
              angular_velocity=np.zeros(3),rotation_mtx=np.eye(3))


def _state(x=0):
    return NS(ball=_physics(x),cars={'blue-0':NS(physics=_physics(x+1),boost_amount=34),
                                     'orange-0':NS(physics=_physics(x+2),boost_amount=30)},
              boost_pad_timers=np.zeros(34),goal_scored=False)

def test_flat_state_comparable():
    a=m.flat_state(_state());assert a.ndim==1 and np.isfinite(a).all()
    assert m.comparison(_state(),_state())['close']

def test_comparison_catches_nontrivial_physics_delta():
    c=m.comparison(_state(0),_state(.1),atol=1e-4)
    assert not c['close'] and c['components_differing']>=3

def test_comparison_rejects_nonfinite():
    a=_state();a.ball.position[0]=np.nan
    with pytest.raises(RuntimeError,match='nonfinite'):m.flat_state(a)

def test_save_guards(tmp_path):
    (tmp_path/'data'/'isolated').mkdir(parents=True)
    assert m.validate_report_path(tmp_path,'data/isolated/new.json').suffix=='.json'
    for p in ('../outside.json','data/../out.json','data/isolated/e.pt'):
        with pytest.raises(ValueError):m.validate_report_path(tmp_path,p)
    m.report_create(tmp_path,'data/isolated/new.json',{'ok':True})
    assert json.loads((tmp_path/'data/isolated/new.json').read_text())=={'ok':True}
    with pytest.raises(FileExistsError):m.report_create(tmp_path,'data/isolated/new.json',{})

def test_gate_consumption_requires_pass_and_expected_kind(tmp_path):
    p=tmp_path/'data'/'isolated';p.mkdir(parents=True)
    f=p/'gate.json'; f.write_text(json.dumps({'version':'v0.3.8a','test':'eight_ticks_batch_vs_eight_single_ticks','passed':True}))
    assert m._load_gate(tmp_path,'data/isolated/gate.json','eight_ticks_batch_vs_eight_single_ticks','passed')['sha256']==m.digest(f)
    with pytest.raises(ValueError,match='did not pass'):
        m._load_gate(tmp_path,'data/isolated/gate.json','different_kind','passed')
    f.write_text(json.dumps({'version':'v0.3.8a','test':'eight_ticks_batch_vs_eight_single_ticks','passed':False}))
    with pytest.raises(ValueError,match='did not pass'):
        m._load_gate(tmp_path,'data/isolated/gate.json','eight_ticks_batch_vs_eight_single_ticks','passed')

def test_obs_gate_accepts_existing_v038(tmp_path):
    p=tmp_path/'data'/'isolated';p.mkdir(parents=True)
    f=p/'obs.json';f.write_text(json.dumps({'version':'v0.3.8','test':'same_state_reference_nexto_vs_teamobserver','allclose':True}))
    assert m._load_gate(tmp_path,'data/isolated/obs.json','same_state_reference_nexto_vs_teamobserver','allclose')['sha256']==m.digest(f)

def test_ablation_rejects_wrong_seed_without_import():
    with pytest.raises(ValueError,match='Invalid ablation'):
        m.benchmark(ROOT,'whatever',seeds=0)
    with pytest.raises(ValueError,match='Invalid ablation'):
        m.benchmark(ROOT,'whatever',horizon=5000)

def test_stress_obs_checks_inputs_before_import_needed(tmp_path):
    with pytest.raises(FileNotFoundError):m.stress_obs(tmp_path)


def test_expected_source_sha_still_matches_original_released_v037a():
    f=ROOT/'slater_nexto_kickoff_v037a.py'
    if f.exists():assert m.digest(f)==m.EXPECTED_V037A
