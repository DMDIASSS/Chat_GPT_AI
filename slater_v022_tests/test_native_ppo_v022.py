import math
from pathlib import Path
import importlib.util
import os
import sys
import numpy as np
import pytest
import torch

FILENAME = Path(__file__).resolve().parents[1] / 'slater_native_ppo_smoke_v022.py'
spec = importlib.util.spec_from_file_location('slater_native_ppo_smoke_v022', FILENAME)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_action_space():
    assert m.ACTION_TABLE.shape == (15, 8)
    assert np.isfinite(m.ACTION_TABLE).all()
    assert np.max(np.abs(m.ACTION_TABLE)) <= 1


def test_observation():
    class Obj: pass
    state=Obj();car=Obj();phys=Obj();ball=Obj()
    phys.position=np.array([0.,0.,17.]); phys.linear_velocity=np.zeros(3)
    phys.angular_velocity=np.zeros(3);phys.forward=np.array([0,1,0])
    car.physics=phys;car.boost_amount=80.;car.on_ground=True
    state.cars={'blue-0':car};state.ball=ball
    ball.position=np.array([0.,100.,93.]);ball.linear_velocity=np.zeros(3)
    o=m.make_observation(state,'blue-0')
    assert o.shape==(m.OBS_SIZE,)
    assert np.isfinite(o).all()
    assert np.isclose(o[15], 0.8) and np.isclose(o[16], 1.0)


def test_gae_correctly_handles_termination_and_bootstrap():
    a,returns=m.gae([1,2,3],[0,0,0],[False,True,False],10,gamma=.9,lam=1.)
    # episode at t=1 is terminal; no influence from t=2
    assert np.allclose(a,[2.8,2,12],atol=1.e-5)
    assert np.allclose(a,returns)


def test_ppo_updates_policy_params():
    torch.manual_seed(123)
    model=m.ActorCritic()
    optimizer=torch.optim.Adam(model.parameters(),lr=0.001)
    rng=np.random.default_rng(123)
    obs=rng.normal(size=(64,m.OBS_SIZE)).astype('float32')
    with torch.no_grad():
        logits,values=model(torch.from_numpy(obs))
        d=torch.distributions.Categorical(logits=logits)
        actions=d.sample()
        oldlp=d.log_prob(actions)
    rows=dict(obs=list(obs),action=actions.tolist(),logp=oldlp.tolist(),
              adv=rng.normal(size=64).astype('float32'),
              ret=rng.normal(size=64).astype('float32'))
    first=model.actor.weight.detach().clone()
    result=m.ppo_update(model,optimizer,rows,torch.device('cpu'),2,32,3)
    assert (model.actor.weight-first).abs().max()>1.e-7
    assert np.isfinite(list(result.values())).all()


def test_out_guard(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    allowed=tmp_path/'data'/'isolated'
    assert m.checked_output('data/isolated/first.pt')==allowed/'first.pt'
    with pytest.raises(ValueError):m.checked_output('data/autoleague/champion.pt')
    with pytest.raises(ValueError):m.checked_output('../outside.pt')
    allowed.mkdir(parents=True)
    (allowed/'first.pt').write_bytes(b'not a checkpoint')
    with pytest.raises(FileExistsError):m.checked_output('data/isolated/first.pt')


class FakeEnv:
    """Deterministic simulated surrogate, NOT RocketSim; tests only wiring."""
    def __init__(self,seed,max_steps=120):
        self.rng=np.random.default_rng(seed);self.max_steps=max_steps
    def reset(self):
        self.step_idx=0;self.reward_sum=0.;self.n_touches=0
        self.o=self.rng.standard_normal(m.OBS_SIZE).astype('float32')
        return self.o.copy()
    def step(self,action):
        self.step_idx+=1
        reward=float(action == 5)-.05
        self.reward_sum+=reward;self.n_touches+=int(action==5)
        done=self.step_idx>=min(self.max_steps,8)
        info=dict(touches=self.n_touches,scored=False,ball_y=0.,
                  total_reward=self.reward_sum,steps=self.step_idx)
        return self.o.copy(),reward,done,info
    def close(self):pass


def test_end_to_end_output_and_no_overwrite(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'SoloShootingEnv',FakeEnv)
    monkeypatch.chdir(tmp_path)
    argv=['slater_native_ppo_smoke_v022.py','--updates','1','--rollout-steps','64',
          '--epochs','1','--minibatch','32','--eval-episodes','2',
          '--out','data/isolated/first.pt']
    monkeypatch.setattr(sys,'argv',argv)
    m.main()
    saved=tmp_path/'data/isolated/first.pt'
    assert saved.exists() and saved.stat().st_size>100
    payload=torch.load(saved,weights_only=True)
    assert payload['meta']['cumulative_env_decisions']==64
    assert payload['meta']['param_delta_l2']>0
    with pytest.raises(FileExistsError):m.main()


def test_spawn_yaw_faces_ball():
    for dx, dy in [(0., 800.), (150., 900.), (-290., 550.), (290., 1050.)]:
        yaw = math.atan2(dy, -dx)
        forward = np.array([math.cos(yaw), math.sin(yaw)])
        toward_ball = np.array([-dx, dy])
        cosine = float(np.dot(forward, toward_ball) / np.linalg.norm(toward_ball))
        assert cosine > .999999
