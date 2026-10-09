"""Offline tests; no RocketSim wheel needed to validate the data path."""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
FAST = Path('/mnt/data/Chat_GPT_AI_Fast_Track')
for p in (HERE, FAST):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import collect_dagger
import distill_v2
from nexto_teacher import nexto_actions


def test_choose_action_teacher_vs_student():
    rng = np.random.default_rng(10)
    assert collect_dagger.choose_student_control(4, 16, 1., rng) == (16, True)
    assert collect_dagger.choose_student_control(4, 16, 0., rng) == (4, False)


def test_unique_shards(tmp_path):
    (tmp_path / 'nexto_rollout_00002.npz').touch()
    (tmp_path / 'ignore.npz').touch()
    assert collect_dagger.find_new_shard(tmp_path) == 3


def test_split_does_not_leak_episodes():
    ids = np.repeat(np.arange(50), 12)
    tr, va = distill_v2.split_episodes(ids, .2, seed=12)
    assert not set(ids[tr]) & set(ids[va])
    assert len(tr) + len(va) == len(ids)


def test_hard_soft_loss():
    import torch
    teacher = torch.tensor([[.8, .2], [.1, .9]])
    pred_correct = torch.tensor([[.8, .2], [.1, .9]])
    pred_wrong = torch.tensor([[.2, .8], [.9, .1]])
    low = distill_v2.combined_loss(pred_correct, teacher, .65)[0]
    high = distill_v2.combined_loss(pred_wrong, teacher, .65)[0]
    assert low < high


def test_dagger_collector_writes_real_shard_schema(tmp_path, monkeypatch):
    from test_teacher import fake_state

    class Engine:
        def __init__(self, **kwargs):
            pass
        def create_base_state(self):
            state = fake_state()
            state.tick_count = 0
            state.goal_scored = False
            for car in state.cars.values():
                car.ball_touches = 0
            return state
        def set_state(self, st, shared):
            self.st = st
            return st
        def step(self, actions, shared):
            assert set(actions) == {1, 2}
            assert all(x.shape == (8, 8) for x in actions.values())
            self.st.tick_count += 8
            return self.st
        def close(self):
            pass

    class Mutator:
        def __init__(self, *args, **kwargs):
            pass
        def apply(self, state, shared):
            pass

    class Obs:
        def reset(self, agents, state, shared):
            pass
        def build_obs(self, agents, state, shared):
            return {a: np.full((92,), a + state.tick_count/100., dtype=np.float32) for a in agents}

    class Policy:
        def __init__(self, path):
            self.obs_count = 92
            self.action_count = 90
        def act(self, x):
            return np.asarray([14], dtype=np.int32)

    class Teacher:
        def __init__(self, device):
            pass
        def observe(self, state, prev):
            assert set(state.cars) == {1, 2}
            return [(a, np.zeros(5), np.zeros(5), np.zeros(5)) for a in state.cars]
        def logits(self, batch):
            out = np.full((len(batch), 90), -5., dtype=np.float32)
            out[:, 16] = 5.
            return out

    m = {}
    for name in ('rlgym', 'rlgym.rocket_league', 'rlgym.rocket_league.sim',
                 'rlgym.rocket_league.state_mutators', 'rlgym.rocket_league.action_parsers',
                 'chatgpt_ai', 'chatgpt_ai.env', 'chatgpt_ai.policy', 'chatgpt_ai.curriculum'):
        m[name] = types.ModuleType(name)
    m['rlgym.rocket_league.sim'].RocketSimEngine = Engine
    m['rlgym.rocket_league.state_mutators'].FixedTeamSizeMutator = Mutator
    m['rlgym.rocket_league.state_mutators'].KickoffMutator = Mutator
    m['rlgym.rocket_league.action_parsers'].LookupTableAction = type('LookupTableAction', (), {
        'make_lookup_table': staticmethod(nexto_actions)})
    m['chatgpt_ai.env'].make_obs = Obs
    m['chatgpt_ai.policy'].LoadedPolicy = Policy
    m['chatgpt_ai.curriculum'].ChatGPTCurriculum = Mutator
    for k, v in m.items():
        monkeypatch.setitem(sys.modules, k, v)
    monkeypatch.setattr(collect_dagger, 'NextoTeacher', Teacher)

    a = SimpleNamespace(checkpoint=Path('unused.pt'), output=tmp_path,
                        decisions=7, episode_decisions=3, save_every=3,
                        teacher_probability=.5, temperature=1., scenarios='grounded',
                        seed=55, teacher_device='cpu')
    collect_dagger.run(a)
    files = sorted(tmp_path.glob('nexto_rollout_*.npz'))
    assert len(files) == 3
    all_ids = []
    all_obs = []
    for file in files:
        with np.load(file) as d:
            assert d['obs'].shape[1:] == (92,)
            assert d['teacher_probs'].shape[1:] == (90,)
            assert np.allclose(d['teacher_probs'].sum(axis=-1), 1., atol=3e-3)
            assert np.all(d['actions'] == 16)
            all_obs.append(d['obs'])
            all_ids.append(d['replay_ids'])
    assert sum(len(x) for x in all_obs) == 7
    assert len(np.unique(np.concatenate(all_ids))) >= 2


def test_dataset_concatenation(tmp_path):
    for i in range(3):
        np.savez_compressed(tmp_path / f'nexto_rollout_{i:05d}.npz',
            obs=np.ones((10, 92), dtype=np.float32) * i,
            teacher_probs=np.ones((10, 90), dtype=np.float32) / 90,
            replay_ids=np.full((10,), i))
    o, p, g = distill_v2.load_data(tmp_path)
    assert o.shape == (30, 92)
    assert p.shape == (30, 90)
    assert len(np.unique(g)) == 3


def test_distillation_end_to_end_synthetic(tmp_path, monkeypatch):
    import torch
    from torch import nn

    class DiscreteFF(nn.Module):
        def __init__(self, n_obs, n_act, hidden, device):
            super().__init__()
            self.model = nn.Sequential(nn.Linear(n_obs, hidden[0]), nn.Tanh(),
                                       nn.Linear(hidden[0], n_act))
            self.to(device)
        def get_output(self, x):
            return torch.softmax(self.model(x), dim=-1)

    fake = {}
    for name in ('rlgym_ppo', 'rlgym_ppo.ppo', 'rlgym_ppo.ppo.discrete_policy',
                 'chatgpt_ai', 'chatgpt_ai.config'):
        fake[name] = types.ModuleType(name)
    fake['rlgym_ppo.ppo.discrete_policy'].DiscreteFF = DiscreteFF
    fake['chatgpt_ai.config'].POLICY_LAYERS = (24, 24)
    for name, module in fake.items():
        monkeypatch.setitem(sys.modules, name, module)

    rng = np.random.default_rng(21)
    obs = rng.normal(size=(200, 92)).astype(np.float32)
    labels = np.where(obs[:, 0] > 0, 16, 25)
    probs = np.full((200, 90), 0.02 / 89, dtype=np.float32)
    probs[np.arange(len(labels)), labels] = .98
    ids = np.repeat(np.arange(10), 20)
    src = tmp_path / 'data.npz'
    out = tmp_path / 'v2.pt'
    np.savez_compressed(src, obs=obs, teacher_probs=probs, replay_ids=ids)
    opts = SimpleNamespace(dataset=src, init=None, output=out,
                           epochs=4, batch=32, learning_rate=.005,
                           weight_decay=0., hard_weight=.65, validation=.2,
                           patience=4, seed=123, device='cpu')
    saved_epoch = distill_v2.train(opts)
    assert saved_epoch is not None
    assert out.is_file()
    loaded = torch.load(out, map_location='cpu', weights_only=True)
    assert 'model.0.weight' in loaded
