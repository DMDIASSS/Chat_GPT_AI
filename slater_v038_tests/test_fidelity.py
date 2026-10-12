from pathlib import Path
import sys
from types import SimpleNamespace as NS
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slater_fidelity_v038 as f
import slater_kickoff_audit_v038 as kickoff
ROOT=Path(__file__).resolve().parents[1]

def phys(pos, inverted=False):
    arr=np.array(pos,dtype=np.float32)
    inv=np.array([-1,-1,1],dtype=np.float32)
    return NS(position=arr*inv if inverted else arr,
       linear_velocity=np.array([30,-10,5],dtype=np.float32)* (inv if inverted else 1),
       angular_velocity=np.array([0,.1,-.1],dtype=np.float32)* (inv if inverted else 1),
       rotation_mtx=np.diag([-1.,-1.,1.]) if inverted else np.eye(3))

def fake_state():
    p1=NS(physics=phys([0,-2560,17]),inverted_physics=phys([0,-2560,17],True),team_num=0,
          is_demoed=False,on_ground=True,ball_touches=0,has_flip=True,boost_amount=33)
    p2=NS(physics=phys([0,2560,17]),inverted_physics=phys([0,2560,17],True),team_num=1,
          is_demoed=False,on_ground=True,ball_touches=0,has_flip=True,boost_amount=100)
    return NS(cars={'blue-0':p1,'orange-0':p2},ball=phys([0,0,93]),
              inverted_ball=phys([0,0,93],True),boost_pad_timers=np.zeros(34))

def test_reference_source_loads_and_builds_correct_shapes():
    path=ROOT/'slater_v038_reference'/'nexto_obs.py'
    mod=f.reference_obs_builder(path)
    state=fake_state(); out=f.reference_obs(state,{},mod)
    assert set(out)=={'blue-0','orange-0'}
    for obs in out.values():
        q,kv,m=f.normalize_obs(obs)
        assert q.shape==(1,32) and kv.shape==(41,24) and m.shape==(41,)
        assert int(m.sum())==4
        assert int((kv[:,3]>.5).sum())==1

def test_reference_is_both_sides_and_prev_action():
    mod=f.reference_obs_builder(ROOT/'slater_v038_reference'/'nexto_obs.py')
    state=fake_state();prev={'orange-0':np.array([1,0,0,0,0,1,1,0],dtype=np.float32)}
    out=f.reference_obs(state,prev,mod)
    np.testing.assert_allclose(out['orange-0'][0][0,24:32],prev['orange-0'])
    np.testing.assert_allclose(out['blue-0'][0][0,24:32],0)

def test_both_equal_and_diff_feature_detection():
    arr=[np.zeros((1,32),np.float32),np.zeros((41,24),np.float32),np.ones(41,np.float32)]
    assert f.compare_obs(arr,arr)['allclose']
    oth=[x.copy() for x in arr]
    oth[1][4,20]=1; oth[2][4]=0;oth[0][0,27]=1
    r=f.compare_obs(arr,oth)
    assert not r['allclose'] and r['mask_mismatch_tokens']==[4]
    assert r['q_mismatching_columns']==[27]
    assert r['kv_feature_mismatches'][0]['feature']=='boost'

def test_guard_output_create_only(tmp_path):
    root=tmp_path;(root/'data'/'isolated').mkdir(parents=True)
    p=f.guarded_path(root,'data/isolated/safe01.json');p.touch()
    with pytest.raises(FileExistsError):f.guarded_path(root,'data/isolated/safe01.json')
    for outside in ('data/safe.json','../escape.json','data/isolated/bad.pt'):
        with pytest.raises(ValueError):f.guarded_path(root,outside)

def test_refuses_other_unvetted_sources(tmp_path):
    p=tmp_path/'nexto_obs.py';p.write_text('print(42)')
    with pytest.raises(ValueError,match='Unverified|Different'):
        f.reference_obs_builder(p)

def test_nexto_kickoff_audit_finds_discrepancies():
    ref=ROOT/'slater_v038_reference'
    sim=ROOT/'slater_nexto_kickoff_v037a.py'
    if not sim.exists():sim=ROOT.parent/'v037a_build'/'slater_nexto_kickoff_v037a.py'
    if not sim.exists():pytest.skip('v037a simulator source not available')
    audit=kickoff.kickoff_audit(ref/'nexto_bot.py',sim,ref/'nexto_obs.py')
    assert audit['reference_defaults']['hardcoded_kickoffs'] is True
    assert audit['reference_defaults']['stochastic_kickoffs'] is True
    assert audit['known_mismatches']>=3
    assert 'DO_NOT_PROMOTE_U62' in audit['decision']

def test_capture_reports_are_not_wrongly_labeled_parity(tmp_path):
    o=f.compare_capture_only(tmp_path)
    assert o['checked']==0 and 'UNVERIFIED' in o['observation_semantic_parity']

