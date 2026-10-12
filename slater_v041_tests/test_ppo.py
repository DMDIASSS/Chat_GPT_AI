import copy

import numpy as np
import pytest
import torch

import slater_ppo as ppo


class Actor(torch.nn.Module):
    def __init__(self):
        super().__init__();self.layer=torch.nn.Linear(32,90)
    def forward(self,x):return self.layer(x[0][:,0])


def fixture():
    torch.manual_seed(55)
    actor=Actor();teacher=copy.deepcopy(actor);critic=ppo.base.ValueNet()
    rng=np.random.default_rng(8);n=32
    q=rng.normal(size=(n,1,32)).astype(np.float32)
    kv=rng.normal(size=(n,41,24)).astype(np.float32)
    mask=np.zeros((n,41),np.float32)
    x=tuple(torch.tensor(v) for v in (q,kv,mask))
    with torch.no_grad():
        dist=torch.distributions.Categorical(logits=actor(x));action=dist.sample()
    rows={'q':list(q),'kv':list(kv),'mask':list(mask),
        'action':action.tolist(),'old_logp':dist.log_prob(action).tolist(),
        'adv':np.linspace(-2,2,n).astype(np.float32),
        'ret':np.linspace(-1,1,n).astype(np.float32)}
    ao=torch.optim.Adam(actor.parameters(),lr=.001)
    co=torch.optim.Adam(critic.parameters(),lr=.001)
    return actor,teacher,critic,ao,co,rows


def test_real_ppo_changes_student_preserves_teacher_and_bounds_drift():
    actor,teacher,critic,ao,co,rows=fixture()
    weights={k:v.clone() for k,v in actor.state_dict().items()}
    fixed={k:v.clone() for k,v in teacher.state_dict().items()}
    result=ppo.trust_region_update(actor,teacher,critic,ao,co,rows,2,8,.3,6,
                                   target_kl=.02)
    assert result['accepted_actor_epochs']>0
    assert result['rollout_policy_kl']<=.02
    assert any(not torch.equal(weights[k],v) for k,v in actor.state_dict().items())
    assert all(torch.equal(fixed[k],v) for k,v in teacher.state_dict().items())


def test_rejected_epoch_restores_weights_and_adam_moments():
    actor,teacher,critic,ao,co,rows=fixture()
    # Populate Adam state first; rejection must restore nonempty moments too.
    ppo.trust_region_update(actor,teacher,critic,ao,co,rows,1,8,.3,6,target_kl=.1)
    weights={k:v.clone() for k,v in actor.state_dict().items()}
    state=copy.deepcopy(ao.state_dict())
    result=ppo.trust_region_update(actor,teacher,critic,ao,co,rows,2,8,.3,7,
                                   target_kl=1e-12)
    assert result['accepted_actor_epochs']==0
    assert result['actor_epoch_rolled_back']
    assert result['rollout_policy_kl']==0
    assert result['rejected_policy_kl']>1e-12
    assert all(torch.equal(weights[k],v) for k,v in actor.state_dict().items())
    for index,moments in state['state'].items():
        for name,value in moments.items():
            assert torch.equal(value,ao.state_dict()['state'][index][name])


def test_nonfinite_update_restores_actor_before_raising(monkeypatch):
    actor,teacher,critic,ao,co,rows=fixture()
    weights={k:v.clone() for k,v in actor.state_dict().items()}
    def corrupt(*args):
        with torch.no_grad():next(actor.parameters()).fill_(float('nan'))
        return {'actor_loss':0.}
    monkeypatch.setattr(ppo.base,'update',corrupt)
    with pytest.raises(RuntimeError,match='Bad native Nexto logits'):
        ppo.trust_region_update(actor,teacher,critic,ao,co,rows,1,8,.3,6)
    assert all(torch.equal(weights[k],v) for k,v in actor.state_dict().items())


@pytest.mark.parametrize('target', [0,-1,float('nan'),float('inf')])
def test_invalid_drift_limit(target):
    with pytest.raises(ValueError):
        ppo.trust_region_update(*fixture(),epochs=1,minibatch=8,
                                teacher_weight=.3,seed=6,target_kl=target)
