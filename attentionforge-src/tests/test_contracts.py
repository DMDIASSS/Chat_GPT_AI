import copy,os
from pathlib import Path
import numpy as np
import torch
import pytest
from attentionforge.runtime import config,batch,meshes,save_checkpoint
from attentionforge.observation import encode,ACTIONS
from attentionforge.model import ActorCritic
from attentionforge.train import gae

def test_action_table():
    assert ACTIONS.shape==(90,8)
    assert len(np.unique(ACTIONS,axis=0))==90
    from attentionforge import _attention_native as n
    np.testing.assert_array_equal(n.action_table(),ACTIONS)

def fixture_state(team=1):
    w=np.zeros((1,1+2*team,32),np.float32)
    w[:,:,9]=1;w[:,:,14]=1
    for i in range(team*2):w[0,i+1,:3]=[i*300,-1800 if i<team else 1800,17];w[0,i+1,15]=40;w[0,i+1,16]=1
    w[0,0,:3]=[200,500,94];p=np.zeros((1,34,2),np.float32);loc=np.zeros((34,4),np.float32)
    return w,p,loc

def test_team_rotation_preserves_features():
    w,p,loc=fixture_state();a,m=encode(w,p,loc)
    # Turn whole field around 180 degrees, swapping blue/orange player roles.
    x=w[:,[0,2,1]].copy()
    for start in (0,3,6,9,12):x[:,:,start:start+2]*=-1
    b,n=encode(x,p,loc)
    # Goal ordering and team-normalized attitude are invariant.
    np.testing.assert_allclose(a[:,0],b[:,1],atol=1e-6);np.testing.assert_array_equal(m[:,0],n[:,1])

def test_no_privileged_opponent_controls_and_padding():
    w,p,loc=fixture_state();a,_=encode(w,p,loc);w[0,2,21:29]=1;b,_=encode(w,p,loc)
    np.testing.assert_array_equal(a[:,0],b[:,0]);assert not np.any(a[:,:,2:4]);assert not np.any(a[:,:,5:7])
    w[0,1,18]=1;w[0,1,15]=0;_,mask=encode(w,p,loc)
    assert not np.any(mask[0,0,ACTIONS[:,5]>0]);assert not np.any(mask[0,0,ACTIONS[:,6]>0]);assert mask.any(-1).all()

def test_attention_is_entity_permutation_invariant_and_receives_gradient():
    torch.set_num_threads(1);w,p,loc=fixture_state(3);o,l=encode(w,p,loc);x=torch.from_numpy(o.reshape(-1,43,40));m=torch.from_numpy(l.reshape(-1,90));net=ActorCritic();a,v=net(x,m)
    perm=torch.arange(43);perm[7:41]=torch.randperm(34)+7;b,z=net(x[:,perm],m)
    torch.testing.assert_close(a,b,atol=2e-6,rtol=1e-4);torch.testing.assert_close(v,z,atol=2e-6,rtol=1e-4)
    (a[:,0].sum()+v.sum()).backward();assert net.blocks[0].attention.in_proj_weight.grad.abs().sum()>0

def test_gae_timeouts_bootstrap_final_state_but_stop_trace():
    r=np.array([[1.],[100.]],np.float32);v=np.array([[2.],[5.]],np.float32);te=np.array([[False],[True]]);tr=np.array([[True],[False]]);tv=np.array([[10.],[0]],np.float32)
    adv,ret=gae(r,v,np.array([999.],np.float32),te,tr,tv,0.9,0.95)
    np.testing.assert_allclose(ret[:,0],[10,100]);np.testing.assert_allclose(adv[:,0],[8,95])

def test_atomic_checkpoint_round_trip(tmp_path):
    net=ActorCritic();opt=torch.optim.Adam(net.parameters());x=torch.randn(2,43,40);x[:,:,39]=1;l=torch.ones(2,90,dtype=torch.bool);net(x,l)[1].sum().backward();opt.step();save_checkpoint(tmp_path/'full.pt',{'model':net.state_dict(),'optimizer':opt.state_dict()})
    a=torch.load(tmp_path/'full.pt',weights_only=False);other=ActorCritic();other.load_state_dict(a['model']);torch.testing.assert_close(net(x,l)[0],other(x,l)[0]);assert a['optimizer']['state']

def has_meshes():
    try:meshes();return True
    except FileNotFoundError:return False
native=pytest.mark.skipif(not has_meshes(),reason='Local Soccar collision meshes are required, not distributed')

@native
def test_native_deterministic_across_worker_counts_and_zero_sum():
    c=config();c['n_envs']=4;c['native_threads']=1;a=batch(c);c['native_threads']=3;b=batch(c);rng=np.random.default_rng(99)
    for _ in range(160):
        ac=rng.integers(0,90,(4,2),dtype=np.int64);x=a.step(ac);y=b.step(ac)
        np.testing.assert_array_equal(x['world'],y['world']);np.testing.assert_array_equal(x['rewards'],y['rewards']);np.testing.assert_allclose(x['rewards'].sum(-1),0,atol=1e-7)

@native
def test_native_goal_direction_and_terminal_potential():
    c=config();c['rewards']={'goal':10.,'approach':2.,'touch':0.,'control_progress':0.};e=batch(c,n=1,kickoffs=True)
    w=e.observe()['world'][0];w[0,:3]=[0,5100,100];w[0,3:6]=[0,1800,0];w[1,:3]=[-2000,-3000,17];w[2,:3]=[2000,3000,17];e.test_state(0,w)
    all_r=0.;g=0
    for _ in range(15):
        r=e.step(np.zeros((1,2),np.int64));all_r+=r['info'][0,3];g+=r['info'][0,0]
        if r['terminated'][0]:break
    assert g==1 and all_r==10;assert r['rewards'][0,0]>9;assert r['terminated'][0] and not r['truncated'][0]
    assert np.all(np.isfinite(r['final_world']))

@native
def test_native_truncation_and_action_delay():
    c=config();c['episode_seconds']=8/120;c['no_touch_seconds']=8/120;e=batch(c,n=1,kickoffs=True);w=e.observe()['world'][0];w[1,:3]=[0,-2000,17];w[2,:3]=[2000,3000,17];e.test_state(0,w)
    idx=int(np.flatnonzero(np.all(ACTIONS==[1,0,0,0,0,0,0,0],axis=1))[0]);r=e.step(np.array([[idx,idx]],np.int64));assert r['truncated'][0] and not r['terminated'][0]
    # Final observation is before reset; reset previous actions are neutral.
    assert r['final_world'][0,1,21]==1;assert r['world'][0,1,21]==0
    # One tick uses zero, seven use throttle. Compare a zero-delay environment.
    c['action_delay']=0;z=batch(c,n=1,kickoffs=True);z.test_state(0,w);s=z.step(np.array([[idx,idx]],np.int64));assert s['final_world'][0,1,3]>r['final_world'][0,1,3]

@native
def test_touch_detection_and_stationary_control_reward():
    c=config();c['rewards']={'goal':0.,'approach':0.,'touch':0.02,'control_progress':0.2};e=batch(c,n=1,kickoffs=True);w=e.observe()['world'][0];w[0,:3]=[0,0,94];w[1,:3]=[-140,0,17];w[1,3:6]=[700,0,0];w[2,:3]=[2000,3000,17];e.test_state(0,w)
    touched=False
    for _ in range(15):
        r=e.step(np.full((1,2),8,np.int64));touched|=bool(r['info'][0,1]);assert abs(r['info'][0,5])<=0.020001
    assert touched
