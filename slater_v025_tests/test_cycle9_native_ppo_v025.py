import copy
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

import slater_cycle9_native_ppo_v025 as m


def test_output_guard_stays_inside_data_isolated(tmp_path):
    root = tmp_path
    root.joinpath('data', 'isolated').mkdir(parents=True)
    p = m.check_output(root / 'data/isolated/test.pt', root)
    assert p == (root / 'data/isolated/test.pt').resolve()
    with pytest.raises(ValueError):
        m.check_output(root / 'data/unsafe.pt', root)
    with pytest.raises(ValueError):
        m.check_output(root / 'data/isolated/test.json', root)
    (root / 'data/isolated/test.pt').write_bytes(b'old')
    with pytest.raises(FileExistsError):
        m.check_output(root / 'data/isolated/test.pt', root)
    with pytest.raises(ValueError):
        m.check_output(root / 'data/isolated/../../bad.pt', root)


def test_save_create_only_no_overwrite(tmp_path):
    path = tmp_path / 'data' / 'isolated' / 'candidate.pt'
    m.save_create_only(path, {'foo': torch.tensor([1.])})
    assert path.is_file()
    assert torch.load(path, weights_only=True)['foo'].item() == 1.
    with pytest.raises((FileExistsError, OSError)):
        m.save_create_only(path, {'foo': torch.tensor([999.])})
    assert torch.load(path, weights_only=True)['foo'].item() == 1.


def test_gae_masks_episode_boundaries():
    # Episode 1 terminates at t=1. Huge reward in episode 2 must not leak into it.
    adv, ret = m.gae([1., 0., 100.], [0., 0., 0.], [False, True, True], 500., gamma=1, lam=1)
    assert np.allclose(adv, [1., 0., 100.])
    assert np.allclose(ret, adv)


def test_gae_bootstrap_truncated_rollout():
    adv, ret = m.gae([1.], [2.], [False], 4., gamma=.5, lam=1)
    assert np.allclose(adv, [1.])
    assert np.allclose(ret, [3.])


def test_value_net_shape_and_grad():
    net = m.ValueNet()
    o = (torch.zeros((3, 1, 32)), torch.zeros((3, 41, 24)), torch.zeros((3, 41)))
    value = net(o)
    assert tuple(value.shape) == (3,)
    assert torch.isfinite(value).all()
    value.mean().backward()
    assert any(p.grad is not None for p in net.parameters())


class FakeScript(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(32, 90)
    def forward(self, inputs):
        return self.linear(inputs[0][:, 0]), None


def test_ppo_gradients_and_teacher_remains_frozen():
    torch.manual_seed(11)
    actor = FakeScript()
    teacher = copy.deepcopy(actor)
    critic = m.ValueNet()
    n = 32
    q = np.random.default_rng(12).normal(size=(n, 1, 32)).astype('float32')
    kv = np.zeros((n, 41, 24), dtype=np.float32)
    mask = np.zeros((n, 41), dtype=np.float32)
    with torch.no_grad():
        logits = m.logits_of(actor, (torch.tensor(q), torch.tensor(kv), torch.tensor(mask)))
        actions = torch.arange(n) % 90
        logps = torch.log_softmax(logits, -1)[torch.arange(n), actions]
    rows = {'q':list(q), 'kv':list(kv), 'mask':list(mask),
            'action':actions.numpy().tolist(),
            'old_logp': logps.numpy().tolist(),
            'adv': np.linspace(-2., 2., n).astype('float32'),
            'ret': np.linspace(-1., 1., n).astype('float32')}
    before = [p.detach().clone() for p in actor.parameters()]
    frozen = [p.detach().clone() for p in teacher.parameters()]
    stats = m.update(actor, teacher, critic, torch.optim.Adam(actor.parameters(), lr=1e-3),
                     torch.optim.Adam(critic.parameters(), lr=1e-3), rows,
                     epochs=2, minibatch=8, teacher_weight=.08, seed=5, device='cpu')
    assert all(np.isfinite(list(stats.values())))
    assert sum(float((p.detach()-b).square().sum()) for p,b in zip(actor.parameters(), before)) > 0
    assert all(torch.equal(p,orig) for p,orig in zip(teacher.parameters(), frozen))


def test_obs_reader_validates_shapes():
    class Observer:
        def observe(self, state, previous):
            return {'blue-0': (np.ones((1,32)),np.ones((41,24)),np.zeros((41,)))}
    q, kv, mask = m.read_obs(None, {}, Observer())
    assert q.shape == (1,32) and kv.shape == (41,24) and mask.shape == (41,)
    class BadObserver:
        def observe(self, state, previous):
            return {'blue-0': (np.ones((32,)),np.ones((41,24)),np.zeros((41,)))}
    with pytest.raises(RuntimeError):
        m.read_obs(None, {}, BadObserver())


def test_no_source_or_replay_io_on_import():
    assert 'data/autoleague' not in m.check_output.__code__.co_consts
    assert m.ACTION_REPEAT == 8
    assert m.S_HORIZON >= 64
