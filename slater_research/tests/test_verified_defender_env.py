"""Offline deterministic smoke tests for the goal-tail environment, no RocketSim needed."""
import copy
import numpy as np
import pytest
from types import SimpleNamespace as NS
from slater_research.replay_engine import Clip, split_replay
from slater_research.verified_defender_env import (
    VerifiedDefenderEnv,validate_catalog_window,ScenarioError)


def sha_train():
    for i in range(1000):
        sha=f'{i:064x}'
        if split_replay(sha)=='train':return sha
    raise AssertionError('No train sha')


def sample():
    sha=sha_train()
    states=[]
    for i in range(4):
        states.append(NS(ball=NS(position=np.array([0.,10.*i,0.]),linear_velocity=np.zeros(3)),
                         cars={1:NS(is_orange=False,ball_touches=0),
                               2:NS(is_orange=True,ball_touches=0)},goal_scored=False))
    ctl=np.zeros((4,2,8),np.float32)
    ctl[:,0,0]=1
    c=Clip(states,ctl,(1,2),1,3,sha)
    meta={'clip_file':'file.npz','replay_sha256':sha,'split':'train','window_s':2*8/120,
          'start_step':1,'reference_goal_step':3,'tail_steps':2,'roster_size':2}
    return c,meta


class FakeEngine:
    def __init__(self):self.state=None;self.closed=False;self.calls=[]
    def set_state(self,state,shared):self.state=copy.deepcopy(state);return self.state
    def step(self,actions,shared):
        assert actions[1].shape==(8,8)
        self.calls.append(copy.deepcopy(actions))
        # if defender uses brake, goal is avoided; neutral and replay score in tail.
        speed=0 if actions[2][0,0]==-1 else 10
        self.state.ball.position[1]+=speed
        self.state.goal_scored=self.state.ball.position[1]>=40
        self.state.cars[2].ball_touches=(len(self.calls)-1)%3==0
        return self.state
    def close(self):self.closed=True


def test_reference_goal_in_tail_and_zero_positive_timeout():
    clip,meta=sample()
    engine=FakeEngine();env=VerifiedDefenderEnv(clip,meta,engine)
    result=env.run_reference()
    assert result.attacker_scored and result.status=='attacker_goal'
    assert result.goal_step==4 and result.goal_offset_s==8/120
    assert result.endpoint_ball_error_uu==0
    assert len(engine.calls)==3 # reference from step 1 -> goal 3 -> tail 4
    assert result.defender_touch_observed
    assert env.i==4
    with pytest.raises(ScenarioError,match='done'):env.step({2:np.zeros(8)})
    env.reset()
    returns=[]
    while not env.done:
        _,reward,done,info=env.step({2:np.array([-1,0,0,0,0,0,0,0],np.float32)})
        returns.append(reward[2])
    assert env.status=='no_goal_by_deadline'
    assert max(returns)<=0.1 and sum(returns)<1.0
    assert not env.result().attacker_scored
    assert not env.result().defender_scored # NOT a confirmed save
    env.close();assert engine.closed


def test_train_only_split_and_metadata_tampering():
    clip,meta=sample()
    assert validate_catalog_window(meta,clip)[0:3]==(1,3,2)
    meta['split']='test'
    with pytest.raises(ScenarioError,match='train-split'):VerifiedDefenderEnv(clip,meta,FakeEngine())
    meta['split']='train';meta['roster_size']=4
    with pytest.raises(ScenarioError,match='roster'):VerifiedDefenderEnv(clip,meta,FakeEngine())
    meta['roster_size']=2;meta['window_s']=5
    with pytest.raises(ScenarioError,match='duration'):VerifiedDefenderEnv(clip,meta,FakeEngine())


def test_bad_controls_rejected_before_physics_mutation():
    clip,meta=sample();engine=FakeEngine();env=VerifiedDefenderEnv(clip,meta,engine)
    with pytest.raises(ScenarioError):env.step({})
    with pytest.raises(ScenarioError):env.step({1:np.zeros(8)})
    with pytest.raises(ScenarioError):env.step({2:np.ones(9)})
    with pytest.raises(ScenarioError):env.step({2:np.array([float('nan')]+[0]*7)})
    with pytest.raises(ScenarioError):env.step({2:np.array([2]+[0]*7)})
    assert len(engine.calls)==0 and env.i==1


def test_repeat_reset_and_source_immutability():
    clip,meta=sample();raw=copy.deepcopy(clip.snapshots)
    engine=FakeEngine();env=VerifiedDefenderEnv(clip,meta,engine)
    a=env.run_reference(); b=env.run_reference()
    assert a==b
    for p,q in zip(raw,clip.snapshots):
        assert np.array_equal(p.ball.position,q.ball.position)
        assert p.goal_scored==q.goal_scored
    # No ghost teleports: each step calls engine.step, not set_state.
    assert len(engine.calls)==6
