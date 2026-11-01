import json
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pandas as pd
import pytest
from slater_native_inspect import Behavior,rollout,write_html,summarize
from slater_replay_input_audit import field_stats,raw_report,bank_fit


def fake_state(car_pos,ball_pos,ball_vel,touched=0,scored=False):
    c=S(physics=S(position=np.array(car_pos,dtype=float),linear_velocity=np.array([1000.,0,0])),boost_amount=50,ball_touches=touched)
    return S(cars={'us':c},ball=S(position=np.array(ball_pos,dtype=float),linear_velocity=np.array(ball_vel,dtype=float)),goal_scored=scored)


def test_moving_is_not_counted_as_scoring_or_shooting():
    b=Behavior(0);s=fake_state([0,0,17],[0,1000,93],[0,0,0]);after=fake_state([100,0,17],[0,1000,93],[0,0,0])
    b.tick(s,after,'us',np.array([1,0,0,0,0,0,0,0]));r=b.result()
    assert r['mean_speed']==1000 and r['travel_distance']==100 and r['goals_for']==r['goalward_contacts']==r['contact_events']==0


def test_contact_edges_and_team_goal_direction_are_distinct():
    b=Behavior(1);before=fake_state([0,0,17],[0,-4000,93],[0,0,0]);after=fake_state([0,0,17],[0,-4000,93],[0,-1000,0],touched=1)
    b.tick(before,after,'us',np.ones(8));b.tick(after,after,'us',np.ones(8))
    assert b.result()['contact_events']==1 and b.result()['touch_ticks']==2 and b.result()['goalward_contacts']==1
    goal=fake_state([0,0,17],[0,-5300,93],[0,-1000,0],scored=True);b.tick(after,goal,'us',np.ones(8))
    assert b.result()['goals_for']==1 and b.result()['goals_against']==0


def test_raw_audit_never_fills_missing_controls():
    df=pd.DataFrame({'throttle':[np.nan,0,127,255],'steer':[np.nan]*4,'boost_is_active':[0,1,1,0]})
    r=raw_report(S(player_dfs={'blue':df}))['blue']
    assert r['recorded_control_fields']['throttle']['nonmissing']==3
    assert r['recorded_control_fields']['steer']['nonmissing']==0
    assert not r['raw_aerial_fields']['pitch']['present']
    assert df.throttle.isna().sum()==1 and df.steer.isna().sum()==4


def test_html_escapes_embedded_replay_text(tmp_path):
    report=dict(records=[],summary=[],note='</script><script>alert(1)</script>');path=tmp_path/'WATCH.html';write_html(report,path)
    text=path.read_text();assert '__REPORT_DATA__' not in text and '<script>alert(1)' not in text and '\\u003c/script>' in text


def test_actual_open_goal_has_dynamic_physics_and_records_controls(tmp_path):
    import slater_native_inspect as module
    class Forward:
        script_ticks=0
        def controls(self,*args):return np.array([1,0,0,0,0,0,1,0],dtype=np.float32)
    original=module.Controller;module.Controller=lambda *args,**kwargs:Forward()
    try:r=rollout(None,None,task='open_goal',side='blue',seed=123,seconds=6)
    finally:module.Controller=original
    assert r['goals_for']==1 and r['contact_events']>0 and r['frames'][-1]['ball'][1]>5120
    assert r['frames'][0]['controls'][0]==1 and r['travel_distance']>100


def test_validation_imitation_ignores_test_partition(tmp_path):
    from slater_native_teacher_repair import bank_rows
    import torch
    from torch import nn
    from slater_native_actor import NativeActor
    # A compatible native module archive; no dependence on downloaded weights.
    path=tmp_path/'checkpoint';path.mkdir()
    shared=nn.Sequential(nn.Linear(230,64),nn.LayerNorm(64),nn.ReLU(),nn.Linear(64,64),nn.LayerNorm(64),nn.ReLU())
    policy=nn.Sequential(nn.Linear(64,64),nn.LayerNorm(64),nn.ReLU(),nn.Linear(64,90))
    torch.jit.script(shared).save(str(path/'SHARED_HEAD.lt'));torch.jit.script(policy).save(str(path/'POLICY.lt'))
    torch.jit.script(nn.Sequential(nn.Linear(64,1))).save(str(path/'CRITIC.lt'));(path/'RUNNING_STATS.json').write_text('{}')
    teacher=tmp_path/'teacher.pt';teacher.write_bytes(b'identity fixture')
    rows=np.zeros((120,231),dtype=np.float32);rows[:,229]=1;rows[:,139+16]=1;rows[80:100,-1]=1;rows[100:,-1]=2
    rows[:,52+19]=1;rows[:,18:52]=0
    # Valid identity rotations in ball/car blocks.
    for offset in [0,52,95]:rows[:,offset+3:offset+12]=np.eye(3).reshape(-1)
    bank=tmp_path/'bank.bin';bank_rows(rows,bank,teacher,{0:[1],1:[2],2:[3]})
    first=bank_fit({'student':path},bank,max_rows=3000)
    rows[100:,139+16]=0;rows[100:,139+8]=1
    second_bank=tmp_path/'other.bin';bank_rows(rows,second_bank,teacher,{0:[1],1:[2],2:[3]})
    second=bank_fit({'student':path},second_bank,max_rows=3000)
    assert first['models']['student']==second['models']['student'] and first['test_used'] is False
    assert first['models']['student']['samples']==20
