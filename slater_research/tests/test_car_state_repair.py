from __future__ import annotations
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from slater_research.car_state_repair import (
    car_body_start, validate_clip_arrays, repair_arrays, select_train_candidates,
    stable_no_jump, flat_floor_candidate, process)


def make_clip(n=2, steps=6, shooter=2):
    width=10+10*n+23+34+46*n
    f=np.zeros((steps,width),dtype=np.float32)
    a=np.zeros((steps,n,8),dtype=np.float32)
    f[:,9]=n
    b=10+10*n
    f[:,b]=np.arange(steps)*8
    for j in range(n):
        base=car_body_start(n,j)
        f[:,base-1]=j+1
        f[:,base]=0 if j % 2 == 1 else 1
        f[:,base+4]=0
        f[:,base+14]=1
        f[:,base+15]=1
        f[:,base+16]=0
        f[:,base+27:base+30]=[0,0,100]
        f[:,base+36:base+45]=np.eye(3,dtype=np.float32).ravel()
    return {'frames':f,'controls':a,'agent_ids':np.arange(1,n+1,dtype=np.int64),
            'shooter_id':np.array(shooter), 'goal_step':np.array(steps-1),
            'ticks_per_step':np.array(8),'replay_sha':np.array('a'*64),
            'inference_warning':np.array('original metadata kept')}


def test_serialization_offsets_multiple_rosters():
    for n in (2,4,6):
        d=make_clip(n)
        assert validate_clip_arrays(d)==(n,5)
        assert car_body_start(n,n-1)+45==d['frames'].shape[1]


def test_stale_jump_flags_only_defenders_are_cleared():
    d=make_clip(); original=copy.deepcopy(d)
    repaired,info=repair_arrays(d,start_step=2,goal_step=5)
    # shooter 2/blue; defender 1/orange. Preserve attacker and other steps.
    b0=car_body_start(2,0);b1=car_body_start(2,1)
    assert info['changed_scalar_values']==8
    assert info['changes']['stale_held_jump_cleared']==4
    assert info['changes']['stale_is_jumping_cleared']==4
    assert np.all(repaired['frames'][2:,b0+14:b0+16]==0)
    assert np.array_equal(repaired['frames'][:2],d['frames'][:2])
    assert np.array_equal(repaired['frames'][:,b1:b1+45],d['frames'][:,b1:b1+45])
    assert np.array_equal(d['frames'],original['frames'])
    assert np.array_equal(repaired['controls'],d['controls'])


def test_jump_edges_preserved():
    d=make_clip()
    d['controls'][3,0,5]=1
    f, info=repair_arrays(d,start_step=2,goal_step=5)
    b=car_body_start(2,0)
    # 2/3/4 excluded due to adjacent jump, 5 repaired.
    assert np.all(f['frames'][2:5,b+14:b+16]==1)
    assert np.all(f['frames'][5,b+14:b+16]==0)


def test_demo_defender_is_excluded():
    d=make_clip()
    b=car_body_start(2,0)
    d['frames'][2:,b+4]=3
    repaired,info=repair_arrays(d,start_step=2,goal_step=5)
    assert not info['trainable_candidate']
    assert info['demo_at_start']==[1]
    assert info['changed_scalar_values']==0
    assert np.array_equal(repaired['frames'],d['frames'])


def test_two_defenders_with_different_teams():
    d=make_clip(n=4,shooter=2)
    f,info=repair_arrays(d,start_step=1,goal_step=5)
    assert set(info['defenders'])=={1,3}
    assert info['changed_scalar_values']==20


def test_ground_mode_requires_flat_upright_and_stable():
    d=make_clip()
    b=car_body_start(2,0)
    d['frames'][:,b+27: b+30]=[0,0,17]
    f,info=repair_arrays(d,start_step=1,goal_step=5,mode='ground_heuristic')
    assert info['changes']['ground_contact_frames_repaired']==4  # t=1..4; last lacks future
    assert np.all(f['frames'][1:5,b+5:b+9]==1)
    assert np.all(f['frames'][5,b+5:b+9]==0)
    d['frames'][:,b+27: b+30]=[3501,0,17]
    f,info=repair_arrays(d,start_step=1,goal_step=5,mode='ground_heuristic')
    assert info['changes'].get('ground_contact_frames_repaired',0)==0


def test_ground_mode_doesnt_make_airborne_grounded():
    d=make_clip();b=car_body_start(2,0)
    d['frames'][:,b+27:b+30]=[0,0,100]
    f,_=repair_arrays(d,start_step=1,goal_step=5,mode='ground_heuristic')
    assert np.all(f['frames'][:,b+5:b+9]==0)


def test_invalid_clip_shapes_finite_and_ids():
    d=make_clip();d['frames']=d['frames'][:,:-1]
    with pytest.raises(ValueError,match='frame shape'):validate_clip_arrays(d)
    d=make_clip();d['frames'][0,-1]=np.nan
    with pytest.raises(ValueError,match='Nonfinite'):validate_clip_arrays(d)
    d=make_clip();d['frames'][:,car_body_start(2,1)-1]=1
    with pytest.raises(ValueError,match='car ID'):validate_clip_arrays(d)


def test_catalog_selection_excludes_holdout():
    c={'schema_version':1,'candidates':[
        {'split':'train','priority':'defender_opportunity_candidate','clip_file':'a.npz'},
        {'split':'validation','priority':'defender_opportunity_candidate','clip_file':'b.npz'},
        {'split':'train','priority':'remote_defender_reference','clip_file':'c.npz'},
        {'split':'test','priority':'defender_opportunity_candidate','clip_file':'d.npz'}]}
    assert [x['clip_file'] for x in select_train_candidates(c)]==['a.npz']


def test_catalog_duplicate_rejected():
    c={'schema_version':1,'candidates':[dict(split='train',priority='defender_opportunity_candidate',clip_file='a.npz')]*2}
    with pytest.raises(ValueError,match='Duplicate'):select_train_candidates(c)


def test_process_never_mutates_source(tmp_path):
    clips=tmp_path/'original';clips.mkdir()
    path=clips/'a.npz'
    data=make_clip()
    with path.open('wb') as h:np.savez_compressed(h,**data)
    before=path.read_bytes()
    cat={'schema_version':1,'candidates':[
        {'clip_file':'a.npz','split':'train','priority':'defender_opportunity_candidate',
         'start_step':2,'reference_goal_step':5,'replay_sha256':'a'*64}]}
    result=process(clips,cat,tmp_path/'derived',limit=1)
    assert result['summary']['selected']==1
    assert result['summary']['original_npz_modified']==0
    assert path.read_bytes()==before
    with np.load(tmp_path/'derived'/'a.npz',allow_pickle=False) as z:
        assert 'state_repair_v020' in z
        assert np.array_equal(z['controls'],data['controls'])
    with pytest.raises(FileExistsError):process(clips,cat,tmp_path/'derived',limit=1)
    with pytest.raises(ValueError):process(clips,cat,clips,limit=1)


def test_wrong_sha_fails_without_writing(tmp_path):
    src=tmp_path/'src';src.mkdir()
    with (src/'f.npz').open('wb') as h:np.savez_compressed(h,**make_clip())
    cat={'schema_version':1,'candidates':[{'clip_file':'f.npz','split':'train',
            'priority':'defender_opportunity_candidate','start_step':2,
            'reference_goal_step':5,'replay_sha256':'b'*64}]}
    with pytest.raises(ValueError,match='hash mismatch'):
        process(src,cat,tmp_path/'derived')
