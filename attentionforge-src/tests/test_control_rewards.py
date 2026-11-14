import copy,json,math
from pathlib import Path
import numpy as np
import pytest
import torch
from attentionforge import _attention_native as native
from attentionforge.runtime import config,batch,save_checkpoint,sha
from attentionforge.reward_experiments import fork_reward
from attentionforge.gpu_profile import model_hash
from attentionforge.model import ActorCritic
from test_contracts import native as needs_meshes


def control_config(style=True):
    c=config('laptop_config.json');c['rewards'].update(profile='control_shots_v1',possession_rate=.2,control_radius=1000.,distance_epsilon=100.,goal_no_floor=1. if style else 0.,goal_speed=.5 if style else 0.,shot_max_age_seconds=6.)
    return c


def test_control_score_bounded_symmetric_and_gated_when_both_far():
    for own,opp in [(0,0),(0,100),(100,0),(100,150),(3000,2000),(1e6,2e6)]:
        x=native.control_value(own,opp,1000,100);y=native.control_value(opp,own,1000,100)
        assert math.isfinite(x) and -1<=x<=1;assert x==pytest.approx(-y,abs=1e-7)
    assert native.control_value(200,2000,1000,100)>native.control_value(2000,200,1000,100)
    assert abs(native.control_value(5000,6000,1000,100))<.001


def test_shot_trace_rejects_floor_opponent_ambiguous_stale_and_own_goals():
    s=native.ShotTrace();assert not s.clean(0,0,720)
    s.observe(1,False,10);assert s.clean(0,20,720);assert not s.clean(1,20,720)
    s.observe(0,True,21);assert not s.clean(0,22,720)
    s.observe(1,False,30);assert s.clean(0,31,720)
    s.observe(2,False,32);assert not s.credited(0,33,720);assert s.clean(1,33,720)
    s.observe(3,False,34);assert not s.credited(0,35,720) and not s.credited(1,35,720)
    s.observe(1,True,40);assert not s.clean(0,41,720)
    s.observe(1,False,50);assert not s.credited(0,771,720)
    s.reset();assert not s.clean(0,0,720)


@needs_meshes
def test_reward_profile_does_not_change_physics_or_observations():
    c=config();c['n_envs']=3;a=batch(c);c['rewards'].update(profile='control_shots_v1',possession_rate=.2,goal_no_floor=1.,goal_speed=.5);b=batch(c)
    rng=np.random.default_rng(391)
    for _ in range(90):
        actions=rng.integers(0,90,(3,2),dtype=np.int64);x=a.step(actions);y=b.step(actions)
        np.testing.assert_array_equal(x['world'],y['world']);np.testing.assert_array_equal(x['pads'],y['pads'])


def shot_fixture(e,kind):
    w=e.observe()['world'][0]
    w[1,:3]=[0,4500,380];w[1,3:6]=[0,1500,0];w[2,:3]=[2500,1000,17]
    w[0,:3]=[0,4640,400];w[0,3:6]=0
    if kind=='bounce':w[0,:3]=[0,4640,120];w[0,3:6]=[0,0,-700];w[1,:3]=[0,4500,100]
    if kind=='untouched':w[1,:3]=[2000,2000,17];w[1,3:6]=0;w[0,:3]=[0,5000,300];w[0,3:6]=[0,2000,0]
    e.test_state(0,w)


@needs_meshes
@pytest.mark.parametrize('kind',['air','bounce','untouched'])
def test_physical_goal_bonuses_match_touch_floor_and_goal_speed(kind):
    c=control_config();e=batch(c,n=1,kickoffs=True);shot_fixture(e,kind);floor=False;touched=False
    for _ in range(60):
        r=e.step(np.full((1,2),8,np.int64));floor|=bool(r['reward_info'][0,7]);touched|=bool(r['info'][0,1])
        if r['terminated'][0]:break
    else:pytest.fail('Fixture did not score')
    info=r['reward_info'][0];assert r['info'][0,0]==1
    if kind=='air':assert touched and not floor and info[2]==1 and info[4]==1 and info[6]==1
    elif kind=='bounce':assert touched and floor and info[2]==0 and info[4]==0 and info[6]==1
    else:assert not touched and info[2]==0 and info[3]==0 and info[6]==0
    if touched:assert info[3]==pytest.approx(.5*min(info[5]/6000,1),rel=1e-5)
    # Sum includes both players' individual approach/touch rewards; remove them
    # to inspect the team-shared, zero-sum control and goal-style components.
    assert r['rewards'][0,0]>=10+info[2]+info[3]+info[1]-1e-5
    assert np.isfinite(r['rewards']).all()


@needs_meshes
def test_control_reward_time_scaling_and_profile_legacy_ablation():
    c=control_config(False);c['rewards'].update(goal=0.,approach=0.,touch=0.);e=batch(c,n=1,kickoffs=True)
    w=e.observe()['world'][0];w[0,:3]=[0,0,93.15];w[1,:3]=[0,-200,17];w[2,:3]=[1500,1500,17];e.test_state(0,w)
    r=e.step(np.full((1,2),8,np.int64));score=r['reward_info'][0,0];dt=r['info'][0,7]/120
    assert r['rewards'][0,0]==pytest.approx(.2*dt*score,rel=1e-5);assert r['rewards'][0,0]==pytest.approx(-r['rewards'][0,1])
    assert r['reward_info'][0,2]==r['reward_info'][0,3]==0


def test_reward_fork_preserves_parent_and_pins_exact_prechange_checkpoint(tmp_path):
    c=config('laptop_config.json');m=ActorCritic(**c['network']);o=torch.optim.Adam(m.parameters());parent=tmp_path/'parent';parent.mkdir()
    state={'config':c,'model':m.state_dict(),'optimizer':o.state_dict(),'learning_transitions':9478144,'updates':163,'history':[],'wandb_id':'parent'}
    save_checkpoint(parent/'latest.pt',state);before=sha(parent/'latest.pt')
    for name,style in [('control',False),('shots',True)]:
        target=tmp_path/name;record=fork_reward(parent,target,state,goal_style=style);new=torch.load(target/'latest.pt',weights_only=False)
        assert model_hash(new['model'])==model_hash(state['model']);assert new['learning_transitions']==9478144 and new['wandb_id'] is None
        assert sha(target/'reward_parent.pt')==before;assert new['config']['rewards']['goal_no_floor']==(1. if style else 0.)
        assert new['config']['ppo']==c['ppo']
    assert sha(parent/'latest.pt')==before and c['rewards'].get('profile')=='rlgym_simple_v1'
