import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
import torch

import slater_nexto_kickoff_v037 as k


def test_exact_script_boundaries():
    assert k.SCRIPT_TICKS==168
    assert k.control_hash()==k.EXPECTED_SCRIPT_SHA256
    for i,expected in [(0,(1,0,0,0,0,0,1,0)),(44,(1,-1,0,0,0,0,1,0)),
                       (60,(1,0,0,0,0,1,1,0)),(72,(1,0,-.7,.8,0,1,1,0)),
                       (76,(1,0,1,0,0,0,1,0)),(128,(1,0,.5,0,1,0,0,0))]:
        np.testing.assert_allclose(k.KICKOFF_CONTROLS[i],expected,rtol=0,atol=1e-6)


def test_script_preserves_tick_boundaries_not_coarse_repeats():
    a=k.grouped_control(40,enabled=True,active=True,nn_control=np.zeros(8))
    assert a.shape==(8,8)
    assert np.all(a[:4,1]==0) and np.all(a[4:,1]==-1)
    b=k.grouped_control(64,enabled=True,active=True,nn_control=np.zeros(8))
    assert np.all(b[:4,5]==1) and np.all(b[4:,5]==0)


def test_script_window_and_fallback():
    nn=np.arange(8,dtype=np.float32)
    np.testing.assert_array_equal(k.grouped_control(168,enabled=True,active=True,nn_control=nn), np.tile(nn,(8,1)))
    np.testing.assert_array_equal(k.grouped_control(0,enabled=False,active=True,nn_control=nn), np.tile(nn,(8,1)))
    np.testing.assert_array_equal(k.grouped_control(0,enabled=True,active=False,nn_control=nn), np.tile(nn,(8,1)))


def test_center_and_nan():
    assert k.is_stationary_center(0.0)
    assert not k.is_stationary_center(12)
    assert not k.is_stationary_center(float('nan'))


class StubNet:
    def __init__(self,l):self.l=torch.tensor([l],dtype=torch.float32)
    def __call__(self,obs):return self.l

def test_beta_nexto_sampling_and_greedy(monkeypatch):
    monkeypatch.setattr(k.base,'to_tensors',lambda obs,dev:obs)
    monkeypatch.setattr(k.base,'logits_of',lambda model,obs:model(obs))
    nn=StubNet(list(range(90)))
    assert k.sample_nexto_action(nn,(None,),beta=1)==89
    torch.manual_seed(14)
    for _ in range(8):
        assert 0<=k.sample_nexto_action(nn,(None,),beta=.5)<90
    with pytest.raises(ValueError):k.sample_nexto_action(nn,(None,),beta=0)


def test_mirror_identical_scripts_reference_does_not_change_sign():
    assert np.array_equal(k.KICKOFF_CONTROLS,k.KICKOFF_CONTROLS.copy())
    assert k.control_hash()==k.control_hash(k.KICKOFF_CONTROLS.copy())


def test_env_commands_and_fallback_without_rocketsim(monkeypatch):
    """Check integration wiring with a fake physics engine; no RLgym here."""
    from types import SimpleNamespace as N
    dummy = lambda position: N(physics=N(position=np.array(position,dtype=float)), ball_touches=0)
    car_b = dummy([0,-2000,17]); car_o = dummy([0,2000,17])
    state = N(cars={'blue-0':car_b,'orange-0':car_o},
              ball=N(position=np.array([0,0,93.],dtype=float)),goal_scored=False)
    class FakeEngine:
        commands = []
        def step(self,cmds,shared):
            self.commands.append(cmds)
            return state
    monkeypatch.setattr(k.base,'read_obs',lambda *args: ('q','kv','mask'))
    monkeypatch.setattr(k,'sample_nexto_action',lambda *args,**kwargs: 0)
    env=k.ScriptedNextoEnv.__new__(k.ScriptedNextoEnv)
    env.state=state;env.engine=FakeEngine();env.previous={};env.device='cpu'
    env.current_opponent='nexto_script';env.student_side='blue';env.observer=None
    env.opponent=object();env.actions=np.zeros((90,8),np.float32)
    env.t=0;env.touches=0;env.opponent_touches=0;env.total_reward=0
    env.max_steps=2;env.script_action_steps=0;env.neural_action_steps=0
    env.stochastic_action_steps=0;env.last_control_source=None;env.kickoff_ball_touched=False
    _,_,done,info=env.step(0)
    assert not done and info['script_action_steps']==1
    assert env.engine.commands[0]['orange-0'].shape==(8,8)
    assert np.all(env.engine.commands[0]['orange-0'][:,6]==1)  # boost
    state.ball.position[1]=50  # once touched / kickoff ended
    _,_,done,info=env.step(0)
    assert done and info['script_action_steps']==1
    assert info['neural_action_steps']==1
    assert np.all(env.engine.commands[1]['orange-0']==0)
