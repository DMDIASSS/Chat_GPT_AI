import json
from pathlib import Path
import numpy as np
import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from rlgym.rocket_league import common_values as cv
from slater_replicar import frames
from slater_versatile_data import parse_one
from slater_v041_core import sha256


def fixture(path,future='blue_goal',unknown=False):
    n=24;columns={'sim_tick':np.arange(n)*8,'clock_phase':['running']*n,'future_segment_end':[future]*n}
    for key,values in [('position',[0,0,93]),('velocity',[0,0,0]),('angular_velocity',[0,0,0]),('rotation',[0,0,0,1])]:
        for axis,value in zip('xyzw',values):columns['ball_'+key+'_'+axis]=np.full(n,value,dtype=np.float32)
    players=[]
    for i in range(2):
        prefix=f'car_{i}_';players.append({'index':i,'team':i,'hitbox':'octane','key':str(i),'name':str(i)})
        for key,values in [('position',[0,-3000 if i==0 else 3000,17]),('velocity',[0,0,0]),('angular_velocity',[0,0,0]),('rotation',[0,0,0,1]),('flip_relative_torque',[0,0,0])]:
            for axis,value in zip('xyzw',values):columns[prefix+key+'_'+axis]=np.full(n,value,dtype=np.float32)
        for key in ['is_jumping','has_jumped','has_double_jumped','has_flipped','previous_controls_jump','is_auto_flipping','is_demoed','is_supersonic']:
            columns[prefix+key]=[False]*n
        for key in ['boosting_time','handbrake_value','supersonic_grace_timer','demo_respawn_timer','jump_ticks','air_time_since_jump','flip_time','auto_flip_timer','auto_flip_torque_scale']:
            columns[prefix+key]=np.zeros(n,np.float32)
        for k in range(4):columns[prefix+f'wheel_{k}_contact']=[True]*n
        for name in ['throttle','steer','pitch','yaw','roll','jump','boost','handbrake']:columns[prefix+'controls_'+name]=np.zeros(n,np.float32)
        columns[prefix+'boost']=np.full(n,50,np.float32)
        columns[prefix+'status']=['active']*n;columns[prefix+'seconds_since_update']=np.zeros(n,np.float32)
        columns[prefix+'ground_controls_source']=['network']*n;columns[prefix+'air_controls_source']=['none' if unknown else 'lookahead']*n
        if unknown:
            for k in range(4):columns[prefix+f'wheel_{k}_contact']=[False]*n
    for k in range(34):columns[f'pad_{k}_cooldown']=np.zeros(n,np.float32)
    header={'format_version':1,'replay_sha256':'a'*64,'groups':['state','game','updates','future'],'players':players,
        'pads':[{'position':list(p),'is_big':p[2]>72} for p in cv.BOOST_LOCATIONS],'rows':'ticks','tick_step':8,'platform':'synthetic-test','final_scores':[999,0]}
    table=pa.table(columns);table=table.replace_schema_metadata({b'replicar':json.dumps(header).encode()});pq.write_table(table,path)


def test_real_parquet_reader_bridge_and_future_labels_excluded(tmp_path):
    a=tmp_path/'a.parquet';b=tmp_path/'b.parquet';fixture(a);fixture(b,'orange_goal')
    info={};left=list(frames(a,info));right=list(frames(b,{}))
    assert len(left)==24 and info['original_replay_sha']=='a'*64
    for (s,c,u),(t,d,v) in zip(left,right):
        np.testing.assert_array_equal(s.ball.position,t.ball.position)
        for aid in s.cars:
            np.testing.assert_array_equal(s.cars[aid].physics.position,t.cars[aid].physics.position)
            np.testing.assert_array_equal(c[aid],d[aid])
    cfg={'per_replay':96,'every':4,'max_age':.05,'max_cost':.55}
    out=tmp_path/'samples.npz';record=parse_one((str(a),sha256(a),str(out),cfg))
    assert record['samples']>0 and record['kind']=='replicar_reconstructed_controls'
    assert record['original_replay_sha']=='a'*64
    assert parse_one((str(a),sha256(a),str(out),cfg))['cached']


def test_unknown_airborne_controls_are_not_invented(tmp_path):
    path=tmp_path/'unknown.parquet';fixture(path,unknown=True)
    rows=list(frames(path,{}));assert rows and all(not controls for _,controls,_ in rows)
