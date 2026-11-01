import copy
from types import SimpleNamespace as NS

import numpy as np
import pytest
import torch

from slater_mechanics_core import MechanicTracker,STAGES,mastery_verdict
from slater_mechanics_env import MechanicsEnv,MechanicsCritic,collect_batched
from slater_mechanics_eval import full_match,retention_check
from slater_mechanics_trainer import DEFAULT_CONFIG,validate_config
from slater_ppo import trust_region_update
from nexto_teacher import nexto_actions


def state():
    def car(pos):
        return NS(is_orange=False,physics=NS(position=np.array(pos,dtype=float),
            linear_velocity=np.array([0.,400.,0.]),rotation_mtx=np.array([[0,-1,0],[1,0,0],[0,0,1.]])),
            boost_amount=80.,ball_touches=0,wheels_with_contact=(False,)*4,
            has_flip=False,has_flipped=False,bump_victim_id=None)
    a=car([0,0,500]);b=car([0,2500,17]);b.is_orange=True
    return NS(cars={'ours':a,'them':b},ball=NS(position=np.array([0.,150.,550.]),
              linear_velocity=np.array([0.,400.,0.])),goal_scored=False)


def test_proximity_without_real_contact_is_not_air_dribble():
    before=state();tracker=MechanicTracker('air_dribble',before,'ours','them')
    for _ in range(180):
        after=copy.deepcopy(before);after.ball.position[1]+=4
        after.cars['ours'].physics.position[1]+=4
        tracker.tick(before,after,np.zeros(8));before=after
    assert not tracker.events.carry_qualified
    assert tracker.events.best_carry_seconds==0


def test_sustained_real_nose_contact_and_progress_complete_carry():
    before=state();tracker=MechanicTracker('air_dribble',before,'ours','them')
    for _ in range(140):
        after=copy.deepcopy(before);after.cars['ours'].ball_touches=1
        after.ball.position[1]+=4;after.cars['ours'].physics.position[1]+=4
        tracker.tick(before,after,np.zeros(8));before=after
    assert tracker.events.success and tracker.events.carry_qualified
    assert tracker.events.nose_contacts>=2
    assert tracker.events.carry_distance>=250


def test_touch_farming_or_hovering_is_not_carry_mastery():
    before=state();before.ball.linear_velocity[:]=0
    before.cars['ours'].physics.linear_velocity[:]=0
    tracker=MechanicTracker('air_dribble',before,'ours','them')
    for _ in range(240):
        after=copy.deepcopy(before);after.cars['ours'].ball_touches=1
        tracker.tick(before,after,np.zeros(8));before=after
    assert not tracker.events.success
    assert tracker.reward_terms.get('guided_carry',0)==0
    assert tracker.reward_terms['nose_contact']<=.61


def test_flip_available_from_start_or_a_floor_landing_is_not_reset():
    before=state();before.cars['ours'].has_flip=True
    tracker=MechanicTracker('reset_acquire',before,'ours','them')
    after=copy.deepcopy(before);after.cars['ours'].wheels_with_contact=(True,)*4
    tracker.tick(before,after,np.zeros(8));assert not tracker.events.reset_acquired
    before=state();tracker=MechanicTracker('reset_acquire',before,'ours','them')
    after=copy.deepcopy(before);after.cars['ours'].physics.position[2]=17
    after.cars['ours'].has_flip=True;after.cars['ours'].wheels_with_contact=(True,)*4
    tracker.tick(before,after,np.zeros(8));assert not tracker.events.reset_acquired


def test_three_wheels_alone_cannot_qualify_as_four_wheel_reset():
    before=state();before.ball.position=np.array([0.,0.,600.])
    before.cars['ours'].physics.rotation_mtx=np.diag([1,-1,-1.])
    tracker=MechanicTracker('reset_acquire',before,'ours','them')
    after=copy.deepcopy(before);after.cars['ours'].has_flip=True
    after.cars['ours'].wheels_with_contact=(True,True,True,False)
    tracker.tick(before,after,np.zeros(8));assert not tracker.events.reset_acquired
    final=copy.deepcopy(after);final.cars['ours'].wheels_with_contact=(True,)*4
    tracker.tick(after,final,np.zeros(8));assert tracker.events.reset_acquired


def test_reset_scoring_chain_requires_a_recent_carry_before_acquisition():
    before=state();before.ball.position=np.array([0.,0.,600.])
    before.cars['ours'].physics.rotation_mtx=np.diag([1,-1,-1.])
    tracker=MechanicTracker('reset_finish',before,'ours','them')
    tracker.events.carry_qualified=True;tracker.seconds=4.;tracker.last_carry=0.
    after=copy.deepcopy(before);after.cars['ours'].has_flip=True
    after.cars['ours'].wheels_with_contact=(True,)*4
    tracker.tick(before,after,np.zeros(8))
    assert tracker.events.reset_acquired
    assert not tracker.carry_before_reset


def test_bump_bonus_requires_real_scored_follow_through():
    before=state();tracker=MechanicTracker('air_bump_finish',before,'ours','them')
    tracker.events.carry_qualified=True;tracker.last_carry=0
    after=copy.deepcopy(before);after.cars['ours'].bump_victim_id='them'
    reward,done=tracker.tick(before,after,np.zeros(8))
    assert tracker.events.useful_bump and not tracker.events.success
    assert 'mechanic_goal' not in tracker.reward_terms
    goal=copy.deepcopy(after);goal.goal_scored=True;goal.ball.position[1]=5300
    tracker.tick(after,goal,np.zeros(8))
    assert tracker.events.success and tracker.reward_terms['mechanic_goal']==12


def test_mastery_clusters_all_rivals_and_sides_by_seed():
    rows=[{'rival':r,'seed':s,'side':side,'success':True}
          for s in range(16) for r in ('nexto','start') for side in ('blue','orange')]
    ok,report=mastery_verdict(rows)
    assert ok and report['pairs']==16
    assert not mastery_verdict(rows[:4])[0]
    rows[0]['success']=False
    assert mastery_verdict(rows)[1]['successful_pairs']==15


class Zero(torch.nn.Module):
    def forward(self,x):return torch.zeros((len(x[0]),90))


@pytest.mark.parametrize('stage',STAGES)
def test_real_scenarios_are_finite_mirrored_and_not_mastered_at_reset(stage):
    rivals={'nexto':Zero()}
    blue=MechanicsEnv(rivals,stage=stage,fixed_side='blue',difficulty=1.)
    orange=MechanicsEnv(rivals,stage=stage,fixed_side='orange',difficulty=1.)
    try:
        a=blue.reset(987);b=orange.reset(987)
        np.testing.assert_allclose(orange.state.ball.position,blue.state.ball.position*np.array([-1,-1,1]),atol=1e-4)
        assert not blue.tracker.events.success
        for _ in range(4):
            obs,reward,done,info=blue.step(0)
            assert np.isfinite(reward) and all(np.isfinite(v).all() for v in obs)
            assert info['script_physics_ticks']==0  # never applies kickoff script to aerial starts
        assert all(np.isfinite(v).all() for v in (*a,*b))
    finally:blue.close();orange.close()


def test_actual_rocket_sim_four_wheel_reset_is_detected():
    from mechanics_scenarios import set_car
    env=MechanicsEnv({'nexto':Zero()},stage='reset_acquire')
    try:
        env.reset(42);s=env.engine.create_base_state();env.teams.apply(s,{})
        env.kickoff.apply(s,{})
        s.ball.position=np.array([0.,0.,750.]);s.ball.linear_velocity=np.zeros(3);s.ball.angular_velocity=np.zeros(3)
        set_car(s.cars['blue-0'],[0,0,625],[0,100,625],up=(0,0,-1),spent_flip=True)
        s.cars['blue-0'].physics.linear_velocity=np.array([0.,0.,200.]);s.cars['blue-0'].flip_time=1.5
        before=env.engine.set_state(s,{})
        assert not before.cars['blue-0'].has_flip
        tracker=MechanicTracker('reset_acquire',before,'blue-0','orange-0')
        for _ in range(80):
            after=env.engine.step({k:np.zeros((1,8),np.float32) for k in before.cars},{})
            tracker.tick(before,after,np.zeros(8));before=after
            if tracker.events.reset_acquired:break
        assert tracker.events.reset_acquired
        assert sum(before.cars['blue-0'].wheels_with_contact)==4
        assert before.cars['blue-0'].has_flip
    finally:env.close()


def test_every_frozen_rival_has_scripted_kickoff_enabled():
    env=MechanicsEnv({'nexto':Zero(),'start':Zero()},retention=True)
    try:
        for seed in (42,43):
            env.reset(seed)
            for _ in range(3):env.step(0)
            assert env.clock.hardcoded and env.clock.script_physics_ticks>0
    finally:env.close()


def test_full_match_keeps_multi_goal_clock_and_draws():
    row=full_match(Zero(),{'nexto':Zero()},rival='nexto',side='blue',seed=42,seconds=8)
    assert row['seconds']==8 and row['kickoffs']>=1
    assert row['script_physics_ticks']>0
    assert row['won'] or row['lost'] or row['draw']


def test_invalid_training_config_rejected():
    cfg=copy.deepcopy(DEFAULT_CONFIG);cfg['target_kl']=float('nan')
    with pytest.raises(ValueError):validate_config(cfg)


def test_regression_against_one_rival_cannot_hide_in_aggregate(monkeypatch):
    import slater_mechanics_eval as evaluation
    candidate=object();reference=object()
    def match(actor,rivals,*,rival,side,seed,seconds):
        # Overall zero change masks a complete regression against one rival.
        delta=(1 if rival=='easy' else -1) if actor is candidate else 0
        return {'goal_diff':delta}
    monkeypatch.setattr(evaluation,'full_match',match)
    result=retention_check(candidate,reference,{'easy':None,'hard':None},
                           seeds=4,seed_base=10,seconds=60)
    assert result['paired_goal_diff_per_minute']['mean']==0
    assert not result['passed']
    assert result['per_rival']['hard']['lower']==-1


def test_batched_rollout_does_not_mix_advantages_between_worlds():
    class World:
        retention=False;task=0;anchor_weight=.02
        def __init__(self,reward):self.reward=reward
        def reset(self,seed):return (np.zeros((1,32),np.float32),
                                    np.zeros((41,24),np.float32),np.zeros(41,np.float32))
        def step(self,action):return self.reset(0),self.reward,False,{'timeout':False}
    class Critic:
        def value_for_task(self,x,tasks):return torch.zeros(len(tasks))
    worlds=[World(1.),World(10.)];obs=[e.reset(0) for e in worlds]
    rows,_,_,_,_=collect_batched(Zero(),Critic(),worlds,obs,[1,2],3)
    assert len(rows['action'])==6
    np.testing.assert_allclose(rows['ret'][3:],rows['ret'][:3]*10,rtol=1e-6)
    assert rows['ret'][2]==1 and rows['ret'][5]==10


def test_only_active_task_value_heads_receive_training_signal():
    class Actor(torch.nn.Module):
        def __init__(self):super().__init__();self.layer=torch.nn.Linear(32,90)
        def forward(self,x):return self.layer(x[0][:,0])
    torch.manual_seed(9);n=32
    actor=Actor();teacher=copy.deepcopy(actor);critic=MechanicsCritic()
    x=(torch.randn(n,1,32),torch.randn(n,41,24),torch.zeros(n,41))
    with torch.no_grad():
        dist=torch.distributions.Categorical(logits=actor(x));actions=dist.sample()
    rows=dict(zip(('q','kv','mask'),[list(v.numpy()) for v in x]))
    rows.update(action=actions.tolist(),old_logp=dist.log_prob(actions).tolist(),
                adv=np.linspace(-1,1,n,dtype=np.float32),ret=np.ones(n,np.float32),
                task=[0,7]*(n//2),anchor_weight=[.02,.3]*(n//2))
    old=critic.heads.weight.detach().clone()
    result=trust_region_update(actor,teacher,critic,
        torch.optim.Adam(actor.parameters(),lr=1e-4),
        torch.optim.Adam(critic.parameters(),lr=1e-4),rows,1,32,.02,9)
    assert result['accepted_actor_epochs']==1
    assert not torch.equal(old[0],critic.heads.weight[0])
    assert not torch.equal(old[7],critic.heads.weight[7])
    assert torch.equal(old[1:7],critic.heads.weight[1:7])
