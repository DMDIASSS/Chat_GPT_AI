"""Offline v0.1.6 catalog tests; no RocketSim dependency."""
import json
import numpy as np
import pytest
from slater_research.scenario_gate import verified_pairs, geometry_from_npz, build_catalog


def row(w,mode,start=10,success=True):
    return {'window_s':w, 'mode':mode, 'start_step':start,
            'reference_goal_step':25,'actual_goal_step':26,
            'post_budget_steps':4,'goal_offset_s':8/120,
            'accepted':success,'endpoint_position_matched':success,
            'entire_reference_window_matched':success,
            'verified_goal_by_deadline':success,'scored_as_reference_team':success,
            'endpoint_ball_error_uu':12.,'max_reference_window_error_uu':27.,
            'error':None}


def test_pair_requires_two_different_successful_modes():
    case={'windows':[row(.5,'ghosted'),row(.5,'all_dynamic',success=False),
                     row(1,'ghosted'),row(1,'all_dynamic')]}
    assert [x['window_s'] for x in verified_pairs(case)]==[1.]


def test_reject_early_goal_and_fake_accept():
    r=row(1,'ghosted');r['actual_goal_step']=24
    d=row(1,'all_dynamic')
    assert verified_pairs({'windows':[r,d]})==[]
    r=row(1,'ghosted');r['max_reference_window_error_uu']=float('nan')
    assert verified_pairs({'windows':[r,d]})==[]


def make_npz(tmp_path, name='example.npz', far=False):
    n=2; width=10+10*n+23+34+46*n
    frames=np.zeros((26,width),np.float32)
    header=10+10*n
    # Team numbers: shooter 1=blue, defender 2=orange.
    frames[:,header+57+46+1]=1
    frames[:,header+5:header+8]=[0,5000,100]
    frames[:,header+57+1+27:header+57+1+30]=[0,4700,100]
    frames[:,header+57+46+1+27:header+57+46+1+30]=[4000 if far else 0,4000,100]
    p=tmp_path/name
    np.savez_compressed(p, frames=frames,goal_step=25,
                        shooter_id=1,ticks_per_step=8,
                        agent_ids=np.array([1,2]),replay_sha=np.array('1'*64))
    return p


def test_geometry_works_with_two_cars(tmp_path):
    p=make_npz(tmp_path)
    feat=geometry_from_npz(p,10,25)
    assert feat['roster_size']==2 and feat['defender_count']==1
    assert feat['start_min_defender_distance_uu']==pytest.approx(1000.)
    assert feat['shot_direction']=='blue_attacking'


def test_catalog_replay_level_split_and_priority(tmp_path):
    p=make_npz(tmp_path)
    report={'schema_version':3,'cases':[{
        'file':p.name,'replay_sha256':'1'*64,
        'windows':[row(1,'ghosted'),row(1,'all_dynamic')]}]}
    out=build_catalog(tmp_path,report)
    assert out['summary']['verified_clip_count']==1
    assert out['candidates'][0]['start_step']==10
    assert out['candidates'][0]['priority']=='defender_opportunity_candidate'


def test_no_unvalidated_goals_and_no_bad_paths(tmp_path):
    make_npz(tmp_path)
    report={'schema_version':3,'cases':[
        {'file':'../escape.npz','windows':[row(1,'ghosted'),row(1,'all_dynamic')]},
        {'file':'example.npz','replay_sha256':'1'*64,'windows':[row(1,'ghosted')]},
    ]}
    c=build_catalog(tmp_path,report)
    assert not c['candidates']
    assert c['summary']['rejections']['invalid_filename']==1


def test_bad_serializer_size_is_rejected(tmp_path):
    p=make_npz(tmp_path)
    with np.load(p) as f:
        obj={k:f[k].copy() for k in f.files}
    obj['frames']=obj['frames'][:,:-2]
    np.savez_compressed(p,**obj)
    with pytest.raises(ValueError,match='serializer mismatch'):
        geometry_from_npz(p,10,25)


def test_overtime_scoreboard_infinity_is_legal(tmp_path):
    p=make_npz(tmp_path)
    with np.load(p) as f:
        obj={k:f[k].copy() for k in f.files}
    obj['frames'][:,0]=float('inf')  # legit overtime game clock in RLGym Tools
    np.savez_compressed(p,**obj)
    assert geometry_from_npz(p,10,25)['roster_size']==2
