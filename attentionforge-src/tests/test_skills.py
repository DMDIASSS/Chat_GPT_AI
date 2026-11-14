import copy,json,math
import numpy as np
import pytest
import torch
from attentionforge import _attention_native as native
from attentionforge.runtime import config,batch
from attentionforge.observation import ACTIONS,encode
from attentionforge.model import ActorCritic
from attentionforge.skills import random_world,tutor,TutorModel,drills
from test_contracts import native as needs_meshes


def test_goal_combo_has_no_repetition_or_alternation_farm():
    c=native.ComboTrace();assert c.goal(0,0)==0
    c.touch(1,10);c.event(0,2,20);assert c.goal(0,21)==.5
    for k in range(30,300):
        c.event(0,2 if k%2 else 4,k)
    assert c.goal(0,300)==1.;c.event(0,8,301);assert c.goal(0,302)==1.5
    assert c.goal(1,302)==0 and c.goal(0,971)==0
    c.touch(2,303);assert c.goal(0,304)==0 and c.goal(1,304)==0
    c.touch(3,305);assert c.goal(0,306)==0 and c.goal(1,306)==0


def test_critic_can_fit_without_corrupting_warm_start_encoder():
    m=ActorCritic(critic_detach=True);x=torch.randn(2,43,40);x[:,:,39]=0;x[:,0,39]=1;x[:,1,39]=2;l=torch.ones(2,90,dtype=torch.bool)
    _,v=m(x,l);v.sum().backward();assert m.critic.weight.grad.abs().sum()>0
    assert m.numeric.weight.grad is None
    m.zero_grad();a,_=m(x,l);a[:,0].sum().backward();assert m.numeric.weight.grad.abs().sum()>0


@needs_meshes
def test_controlled_pose_injection_rotates_car_and_restarts_all_episode_clocks():
    c=config('laptop_config.json');c['episode_seconds']=1;c['no_touch_seconds']=1;e=batch(c,n=1)
    w=random_world(np.random.default_rng(3),1)[0]
    for _ in range(2):
        e.set_ground(0,w);r=e.observe()
        np.testing.assert_allclose(r['world'][0,1:,9:15],w[1:,9:15],atol=2e-6)
        for k in range(10):
            r=e.step(np.full((1,2),8,np.int64));assert not r['truncated'][0]


@needs_meshes
def test_tutor_is_ground_only_and_reaches_real_ball_on_both_colors():
    c=config('laptop_config.json');r=drills(TutorModel(),c,n=8,seed=701711)
    assert all(x['contact_fraction']>=.5 for x in r.values())
    e=batch(c,n=3);raw=e.observe();ob,lm=encode(raw['world'],raw['pads'],e.pad_locations());a=tutor(torch.from_numpy(ob.reshape(-1,43,40)),torch.from_numpy(lm.reshape(-1,90))).numpy()
    assert not ACTIONS[a,5].any()


@needs_meshes
def test_skill_reward_counts_actual_contact_and_resets():
    c=config('laptop_config.json');c['rewards'].update(profile='skills_v1',touch=1.,approach=1.);e=batch(c,n=1,kickoffs=True)
    w=e.observe()['world'][0];w[0,:3]=[0,0,94];w[1,:3]=[-140,0,17];w[1,3:6]=[700,0,0];w[2,:3]=[2000,3000,17];e.test_state(0,w)
    total=0
    for k in range(15):
        r=e.step(np.full((1,2),8,np.int64));total+=r['skill_info'][0,0];assert np.isfinite(r['rewards']).all()
    assert total>0
    e.skill_stage(1.);e.drill_fraction(.15)
    for bad in [-1.,float('nan'),2.]:
        with pytest.raises(ValueError):e.skill_stage(bad)


def test_rlbot5_clock_and_public_packet_parity():
    f=pytest.importorskip('rlbot.flat')
    from attentionforge.rlbot5_agent import packet_observation,PolicyClock
    def ph(x,y,yaw=0):return f.Physics(location=f.Vector3(x,y,17),rotation=f.Rotator(0,yaw,0),velocity=f.Vector3(),angular_velocity=f.Vector3())
    players=[f.PlayerInfo(physics=ph(0,-1000,math.pi/2),team=0,boost=33,air_state=f.AirState.OnGround),f.PlayerInfo(physics=ph(0,1000,-math.pi/2),team=1,boost=33,air_state=f.AirState.OnGround)]
    p=f.GamePacket(players=players,balls=[f.BallInfo(physics=ph(0,0))],boost_pads=[f.BoostPadState(True,0) for _ in range(34)],match_info=f.MatchInfo(frame_num=100))
    locations=np.zeros((34,4),np.float32);x,l=packet_observation(p,0,locations,np.zeros(8,np.float32))
    assert x.shape==(1,43,40) and l.shape==(1,90);assert x[0,0,15]==pytest.approx(.33);assert x[0,0,16]==1
    class Fixed(torch.nn.Module):
        def forward(self,x,l):
            z=torch.zeros(len(x),90);z[:,16]=1;return z,torch.zeros(len(x))
    clock=PolicyClock(Fixed(),{'tick_skip':8,'action_delay':1},locations)
    np.testing.assert_array_equal(clock.controls(p,0),0);assert clock.decisions==1
    p=f.GamePacket(players=p.players,balls=p.balls,boost_pads=p.boost_pads,match_info=f.MatchInfo(frame_num=101));np.testing.assert_array_equal(clock.controls(p,0),ACTIONS[16]);assert clock.decisions==1
    p=f.GamePacket(players=p.players,balls=p.balls,boost_pads=p.boost_pads,match_info=f.MatchInfo(frame_num=108));clock.controls(p,0);assert clock.decisions==2
    p=f.GamePacket(players=p.players,balls=p.balls,boost_pads=p.boost_pads,match_info=f.MatchInfo(frame_num=0));np.testing.assert_array_equal(clock.controls(p,0),0);assert clock.decisions==1
    # Orange sees identical ego-relative geometry after whole-field rotation.
    y,_=packet_observation(p,1,locations,np.zeros(8,np.float32));np.testing.assert_allclose(x[:,0:7],y[:,0:7],atol=1e-6,rtol=1e-5)


def test_recovery_archives_failed_checkpoints_restores_best_and_has_retry_limit(tmp_path,monkeypatch):
    import attentionforge.train as trainer
    from attentionforge.skills import run
    from attentionforge.runtime import save_checkpoint,atomic_json
    from attentionforge.train import load
    c={'ppo':{'learning_rate':.00002}};s={'config':c,'model':{'v':torch.tensor(0.)},'optimizer':{'param_groups':[{'lr':.00002}]},'learning_transitions':0,'updates':0,'training_wall_seconds':0,'physics_ticks':0,'env_decisions':0,'history':[]}
    save_checkpoint(tmp_path/'latest.pt',s);save_checkpoint(tmp_path/'best_contact.pt',s);atomic_json(tmp_path/'config.json',c)
    calls=[]
    def fail(cfg,folder):
        a=load(folder/'latest.pt',torch.device('cpu'));a['model']['v']+=1;a['learning_transitions']+=100;a['updates']+=1
        save_checkpoint(folder/'latest.pt',a);atomic_json(folder/'skill_regression.json',{'minimum_contact_fraction':0.});calls.append(1)
    monkeypatch.setattr(trainer,'train',fail);run(tmp_path)
    a=load(tmp_path/'latest.pt',torch.device('cpu'));assert len(calls)==3
    assert a['model']['v']==0 and a['learning_transitions']==300 and a['recovery_attempts']==3
    assert a['config']['ppo']['learning_rate']==.000003
    assert len(list((tmp_path/'regressions').glob('*.pt')))==3


def test_v5_exports_get_distinct_agent_ids_so_rlbot_cannot_group_different_models(tmp_path):
    import tomllib
    from attentionforge.export_v5 import write
    m=torch.jit.script(ActorCritic(width=32,heads=4,blocks=1))
    ids=[]
    for name in ('candidate','baseline'):
        out=tmp_path/name;out.mkdir();write(out,m)
        local=tomllib.loads((out/'bot.bot.toml').read_text());portable=tomllib.loads((out/'bot.portable.bot.toml').read_text());runtime=json.loads((out/'runtime_v5.json').read_text())
        assert local['settings']['agent_id']==portable['settings']['agent_id']==runtime['agent_id'];ids.append(runtime['agent_id'])
        torch.jit.load(str(out/'actor.lt'))
    assert ids[0]!=ids[1]


@needs_meshes
def test_skill_touch_acceleration_matches_upstream_advanced_touch():
    from types import SimpleNamespace as S
    from rlgym_tools.rocket_league.reward_functions.advanced_touch_reward import AdvancedTouchReward
    c=config('laptop_config.json');c['rewards'].update(profile='skills_v1',goal=0.,touch=1.,approach=0.);e=batch(c,n=1,kickoffs=True)
    w=e.observe()['world'][0];w[0,:3]=[0,0,94];w[1,:3]=[-140,0,17];w[1,3:6]=[700,0,0];w[2,:3]=[2000,3000,17];e.test_state(0,w)
    ref=AdvancedTouchReward(touch_reward=0,acceleration_reward=.5,use_touch_count=False)
    before=e.observe()['world'][0,0,3:6].copy();ref.reset([0,1],S(ball=S(linear_velocity=before)),{})
    for _ in range(12):
        raw=e.step(np.full((1,2),8,np.int64));state=S(ball=S(linear_velocity=raw['final_world'][0,0,3:6].copy()),cars={a:S(ball_touches=int(raw['info'][0,1+a])) for a in (0,1)})
        expected=ref.get_rewards([0,1],state,{},{},{})
        assert raw['skill_info'][0,1]==pytest.approx(sum(expected.values()),abs=1e-5)
