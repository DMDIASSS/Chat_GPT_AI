import copy
import numpy as np
import pytest
from duelforge.runtime import config,ROOT,batch
from duelforge.potential import estimate,ball_prediction,reach_times,PotentialReward,BALL_RADIUS

def cfg():return config(ROOT/'config_potential.json')
def world():
    w=np.zeros((1,3,32),np.float32);w[0,0,2]=BALL_RADIUS
    w[0,1,:3]=[0,-700,17];w[0,2,:3]=[0,1800,17]
    w[0,1,9:12]=[0,1,0];w[0,2,9:12]=[0,-1,0];w[0,1:,12:15]=[0,0,1];w[0,1:,15]=30;w[0,1:,16]=1;w[0,1:,29]=1
    return w

def test_equal_time_and_obvious_advantage_sides():
    w=world();r=estimate(w,cfg());assert r['eta'][0,0]<r['eta'][0,1] and r['phi'][0]>0
    w[:,2,1]=700;r=estimate(w,cfg());np.testing.assert_allclose(r['eta'][:,0],r['eta'][:,1]);assert abs(r['phi'][0])<1e-6
    w[:,2,1]=200;r=estimate(w,cfg());assert r['phi'][0]<0

def test_side_rotation_is_antisymmetric():
    w=world();a=estimate(w,cfg());v=w.copy();v[:,:,:15]*=np.asarray([-1,-1,1]*5,np.float32);v[:,[1,2]]=v[:,[2,1]];b=estimate(v,cfg())
    np.testing.assert_allclose(a['eta'],b['eta'][:,::-1],atol=1e-6);np.testing.assert_allclose(a['phi'],-b['phi'],atol=1e-6)

def test_ground_boost_and_turn_cost_have_effect():
    w=world();w[0,1,1]=-1800;w[0,2,1]=2500;w[:,:,15]=0;a=estimate(w,cfg())
    w[0,1,15]=100;b=estimate(w,cfg());assert b['eta'][0,0]<=a['eta'][0,0]
    w[0,1,9:12]=[1,0,0];c=estimate(w,cfg());assert c['eta'][0,0]>=b['eta'][0,0]

def test_high_ball_unreachable_at_short_horizon_without_jump_or_boost():
    w=world();w[0,0,2]=1700;w[0,1:,29]=0;w[0,1:,15]=0;c=cfg();c['predictive']['horizon']=1.
    r=estimate(w,c);assert not r['reachable'].any();assert np.isfinite(r['phi']).all()

def test_ball_ground_wall_and_stationary_floor_predictions():
    w=world();points,t,g,q=ball_prediction(w);np.testing.assert_allclose(points[:,:,2],BALL_RADIUS,atol=1e-4)
    w[0,0,:3]=[3800,0,700];w[0,0,3:6]=[1500,0,-200];p,_,_,_=ball_prediction(w)
    assert (p[:,:,2]>=BALL_RADIUS-1e-4).all();assert np.abs(p[:,:,0]).max()<=4096-BALL_RADIUS+1e-3;assert p[0,-1,0]<p[0,0,0]

def test_moving_ball_and_zero_sum_finite():
    w=world();w[0,0,3:6]=[100,1800,100];r=estimate(w,cfg());assert np.isfinite(r['eta']).all() and np.abs(r['phi']).max()<=1

def test_true_terminal_and_timeout_shaping_no_reset_leak():
    c=cfg();w=world();before={'world':w};pr=PotentialReward(c,before);phi=pr.current['phi'].copy();different=world();different[0,1,1]=-3000
    def raw(terminal,truncated):return {'world':different.copy(),'final_world':w.copy(),'info':np.asarray([[0,0,0,8,5,8]],np.float32),'reward_parts':np.zeros((1,2,3),np.float32),'terminated':np.array([terminal]),'truncated':np.array([truncated])}
    out=pr.apply(raw(True,False));expected=-c['predictive']['shaping_weight']*phi
    np.testing.assert_allclose(out['rewards'][:,0],expected);np.testing.assert_allclose(out['rewards'].sum(-1),0,atol=1e-7)
    pr=PotentialReward(c,before);out=pr.apply(raw(False,True));np.testing.assert_allclose(out['rewards'][:,0],c['predictive']['shaping_weight']*(c['ppo']['gamma']-1)*phi,atol=1e-7)
    np.testing.assert_allclose(pr.current['phi'],estimate(different,c)['phi'])

def test_discounted_potential_telescopes_and_zero_ticks_do_not_pay():
    c=cfg();w=world();pr=PotentialReward(c,{'world':w});initial=pr.current['phi'][0];total=0.;gamma=c['ppo']['gamma']
    for k in range(5):
        nxt=w.copy();nxt[0,1,1]+=100*(k+1);raw={'world':nxt,'final_world':nxt,'info':np.asarray([[0,0,0,8,5,8]],np.float32),'reward_parts':np.zeros((1,2,3),np.float32),'terminated':np.array([k==4]),'truncated':np.array([False])};out=pr.apply(raw);total+=gamma**k*out['rewards'][0,0]
    assert total==pytest.approx(-c['predictive']['shaping_weight']*initial,abs=1e-6)
    raw['info'][:,3]=0;raw['terminated'][:]=False;out=pr.apply(raw);np.testing.assert_array_equal(out['rewards'],0)

def test_native_wrapper_smoke_and_scene_reset():
    c=cfg();c['n_envs']=2;e=batch(c);e.scene(0)
    for _ in range(10):
        r=e.step(np.full((2,2),16,np.int64));assert np.isfinite(r['rewards']).all();np.testing.assert_allclose(r['rewards'].sum(-1),0,atol=1e-6)


def test_invalid_physics_rejected_instead_of_nan_reward():
    w=world();w[0,0,0]=np.nan
    with pytest.raises(ValueError):estimate(w,cfg())


def test_component_ablation_and_invalid_mixture():
    from duelforge.runtime import validate
    c=cfg();c['predictive']['intercept_weight']=1.;c['predictive']['threat_weight']=0
    r=estimate(world(),c);np.testing.assert_allclose(r['phi'],r['intercept'],atol=1e-6)
    c['predictive']['intercept_weight']=0;r=estimate(world(),c);np.testing.assert_array_equal(r['phi'],0)
    c['predictive']['intercept_weight']=1.;c['predictive']['threat_weight']=.1
    with pytest.raises(ValueError):validate(c)
