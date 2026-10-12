"""Offline regression tests for Slater v0.4.0. No rlgym installation required."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
# The pre-existing project-root modules are on sys.path when tests run on Windows.
import slater_v040_multirival as m


def test_default_rivals():
    assert m.normalize_modes(','.join(m.RIVALS)) == m.RIVALS
    assert 'frozen_u60' in m.RivalEnv.VALID_MODES
    assert 'nexto_script' in m.RivalEnv.VALID_MODES


@pytest.mark.parametrize('modes', [
    '', 'nexto_greedy', 'nexto_script,nexto_script',
    'nexto_script,cycle9', 'frozen_u60,cycle9',
    'nexto_script,frozen_u60,rocket_bot',
])
def test_unsafe_modes_rejected(modes):
    with pytest.raises(ValueError):
        m.normalize_modes(modes)


def test_timeout_bootstrap_vs_goal():
    assert m.adjusted_timeout_reward(1., True, True, 4., gamma=.9) == pytest.approx(4.6)
    assert m.adjusted_timeout_reward(1., True, False, 4., gamma=.9) == 1.
    assert m.adjusted_timeout_reward(1., False, False, 4., gamma=.9) == 1.
    with pytest.raises(ValueError):
        m.adjusted_timeout_reward(1., False, True, 0.2)
    with pytest.raises(FloatingPointError):
        m.adjusted_timeout_reward(float('nan'), True, True, 1.)


def test_time_limit_bootstrap_gae_not_leak():
    # Baseline: final timeout has bootstrap V=4, not a true terminal value of zero.
    corrected = [0., m.adjusted_timeout_reward(1., True, True, 4., gamma=.9), 0.]
    a, _ = m.base.gae(corrected, [0., 0., 0.], [False, True, False], 0., gamma=.9, lam=1.)
    assert a[1] == pytest.approx(4.6, rel=1e-6)
    assert a[0] == pytest.approx(4.14, rel=1e-6)
    assert a[2] == pytest.approx(0.)


def test_frozen_u60_controls_use_independent_model(monkeypatch):
    e = m.RivalEnv.__new__(m.RivalEnv)
    e.current_opponent = 'frozen_u60'
    e.frozen_u60 = object()
    e.state = object()
    e.previous = {}
    e.observer = object()
    e.device = 'cpu'
    e.neural_action_steps = 0
    e.last_control_source = None
    e.actions = np.arange(90 * 8, dtype=np.float32).reshape(90, 8)
    monkeypatch.setattr(m.base, 'read_obs', lambda *args: 'dummy')
    monkeypatch.setattr(m.base, 'to_tensors', lambda *args: 'dummy_tensors')
    monkeypatch.setattr(m.base, 'logits_of', lambda *args: torch.arange(90, dtype=torch.float32).reshape(1,90))
    cmds = e._opponent_commands('orange-0')
    assert cmds.shape == (m.base.ACTION_REPEAT, 8)
    np.testing.assert_array_equal(cmds[0], e.actions[89])
    assert np.all(cmds == cmds[0])
    assert e.neural_action_steps == 1
    assert e.last_control_source == 'frozen_u60'


def test_frozen_u60_mode_selection(monkeypatch):
    def fake_parent_reset(self, seed):
        self.episode_count += 1
        index = self.episode_count - 1
        self.student_side = self.fixed_side or ('blue' if index%2==0 else 'orange')
        self.current_opponent = self.modes[(index//2)%len(self.modes)]
        self.opponent = 'nexto_model'
        return 'obs'
    monkeypatch.setattr(m.prev.ScriptedNextoEnv, 'reset', fake_parent_reset)
    e = m.RivalEnv.__new__(m.RivalEnv)
    e.episode_count = 0
    e.fixed_side = None
    e.frozen_u60 = 'frozen_model'
    e.modes = m.RIVALS
    pairs = []
    for i in range(8):
        obs = e.reset(100+i)
        pairs.append((e.current_opponent, e.student_side, e.opponent))
    assert [x[0] for x in pairs] == [x for x in m.RIVALS for _ in range(2)]
    assert [x[1] for x in pairs] == ['blue','orange']*4
    assert pairs[-1][-1] == 'frozen_model'
    assert pairs[-2][-1] == 'frozen_model'


def test_collect_continuous_no_implicit_reset(monkeypatch):
    shapes = ((1,32), (41,24), (41,))
    def obs():
        return tuple(np.zeros(s, dtype=np.float32) for s in shapes)

    class StubEnv:
        def __init__(self):
            self.index = 0
            self.resets = []
        def step(self, a):
            self.index += 1
            return obs(), 1., self.index == 3, {'timeout': self.index == 3, 'outcome':0}
        def reset(self, seed):
            self.resets.append(seed)
            return obs()

    class ConstantValue:
        def __call__(self, x):
            return torch.tensor([2.0])

    monkeypatch.setattr(m.base, 'choose', lambda actor, critic, obs, device: (7, -0.5, 2.0))
    env = StubEnv()
    rows1, end1, last1, seed1, tr1 = m.collect_continuous(None, ConstantValue(), env, obs(), 123, 2)
    assert len(rows1['action']) == 2
    assert len(end1) == 0
    assert env.resets == []
    assert seed1 == 123 and tr1 == 0
    rows2, end2, last2, seed2, tr2 = m.collect_continuous(None, ConstantValue(), env, last1, seed1, 2)
    assert len(end2) == 1 and tr2 == 1
    assert env.resets == [124]
    assert rows2['reward'][0] == pytest.approx(1 + m.GAMMA * 2)
    assert rows2['done'] == [True, False]
    assert seed2 == 124


def test_immutability_guard():
    p = torch.nn.Parameter(torch.tensor([1.0]))
    module = torch.nn.Linear(1,1)
    copies = [x.detach().clone() for x in module.parameters()]
    assert m.params_unchanged(module, copies)
    with torch.no_grad():next(module.parameters()).add_(1.)
    assert not m.params_unchanged(module, copies)


def test_validate_bad_time_and_checkpoint_options():
    parser = m.make_parser()
    ok = parser.parse_args(['--run','v040_smoke01','--updates','2', '--rollout-steps','512',
                            '--max-train-seconds','700'])
    assert m.validate_args(ok) == m.RIVALS
    invalid = parser.parse_args(['--run','v040_smoke01','--max-train-seconds','-1'])
    with pytest.raises(ValueError):m.validate_args(invalid)
    invalid = parser.parse_args(['--run','v040_smoke01','--updates','0'])
    with pytest.raises(ValueError):m.validate_args(invalid)


def test_run_name_create_only(tmp_path):
    p = tmp_path/'data'/'isolated'
    p.mkdir(parents=True)
    assert m.check_output_prefix(tmp_path, 'training01') == p
    (p/'training01_u0062.pt').touch()
    with pytest.raises(FileExistsError):m.check_output_prefix(tmp_path, 'training01')


def test_no_actor_deepcopy_or_checkpoint_overwrite():
    src = (HERE/'slater_v040_multirival.py').read_text()
    assert 'copy.deepcopy' not in src
    assert 'torch.save(' not in src # centralized create-only helper only
    assert 'EXPECTED_V60_SHA256' in src
    assert 'base.save_create_only' in src
    assert 'weights_only=False' not in src


def test_end_to_end_synthetic_training_writes_checkpoint(tmp_path, monkeypatch):
    """Exercise the *actual* PPO optimizer, the CLI orchestration and .pt saving.

    Replaces only RocketSim, external model loading and costly evaluations.
    This cannot substitute for a real Windows RocketSim smoke run.
    """
    import copy
    import json
    import types

    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = torch.nn.Linear(32, 90)
        def forward(self, x):
            q,kv,mask=x
            return self.linear(q[:,0,:])

    class FakeEnv:
        def __init__(self, actions, observer, originals, frozen_u60, max_steps, device='cpu', modes=m.RIVALS):
            self.i = 0
            self.total = 0
            self.modes = modes
            self.episode_count = 0
            self.active = self.modes[0]
            self.closed = False
        def reset(self, seed):
            self.i = 0
            self.active = self.modes[(self.episode_count//2) % len(self.modes)]
            self.episode_count += 1
            return self.obs()
        def obs(self):
            q=np.zeros((1,32), dtype=np.float32)
            q[0,0] = (self.total % 17)/17.
            return (q, np.zeros((41,24),dtype=np.float32), np.zeros(41,dtype=np.float32))
        def step(self, action):
            self.i += 1
            self.total += 1
            done=self.i >= 16
            return self.obs(), .1, done, {'timeout':bool(done), 'outcome':0,
                                          'opponent':self.active,
                                          'script_action_steps':1 if self.active=='nexto_script' else 0}
        def close(self):
            self.closed=True

    isolated=tmp_path/'data'/'isolated'
    isolated.mkdir(parents=True)
    source=isolated/'source_u0060.pt'
    source.write_bytes(b'dummy checkpoint artifact')
    vendor=tmp_path/'vendor'/'nexto'
    vendor.mkdir(parents=True)
    (vendor/'nexto-model.pt').write_bytes(b'dummy Nexto fixture')
    cycle=tmp_path/'cycle9_ref.pt'
    cycle.write_bytes(b'dummy Cycle9 fixture')

    tiny=TinyActor()
    critic=m.base.ValueNet()
    actor_opt=torch.optim.Adam(tiny.parameters())
    critic_opt=torch.optim.Adam(critic.parameters())
    doc={'actor':tiny.state_dict(), 'critic':critic.state_dict(),
         'actor_optimizer':actor_opt.state_dict(),
         'critic_optimizer':critic_opt.state_dict(), 'global_updates':60}
    provenance={'candidate_sha':m.base.sha256(source),
                'source_sha':m.base.sha256(cycle),
                'nexto_sha':m.base.sha256(vendor/'nexto-model.pt'),
                'script_sha256':m.prev.control_hash()}
    def fake_load(root,checkpoint):
        student=TinyActor()
        student.load_state_dict(doc['actor'])
        cycle9=TinyActor()
        nexto=TinyActor()
        return student,cycle9,nexto,np.ones((90,8),dtype=np.float32),doc,provenance
    monkeypatch.setattr(m.prev,'load_protected',fake_load)
    def fake_anchor(path,state,actor):
        anchor=TinyActor()
        anchor.load_state_dict(state)
        return anchor
    monkeypatch.setattr(m,'load_original_v60_anchor',
                        lambda root,actor,**kwargs:(fake_anchor(None,doc['actor'],actor),m.base.sha256(source)))
    monkeypatch.setattr(m,'RivalEnv',FakeEnv)
    monkeypatch.setattr(m,'compare_policies',lambda *args,**kwargs:{'summary':{'test':'mocked'}})
    fake_obs_module=types.ModuleType('afk_team_research')
    fake_obs_module.TeamObserver=type('TeamObserver',(),{})
    monkeypatch.setitem(sys.modules,'afk_team_research',fake_obs_module)
    checkmod=types.ModuleType('slater_research.checkpoint')
    checkmod.CYCLE9='cycle9_ref.pt'
    monkeypatch.setitem(sys.modules,'slater_research.checkpoint',checkmod)
    monkeypatch.chdir(tmp_path)
    m.run(['--from-checkpoint','data/isolated/source_u0060.pt',
           '--anchor-checkpoint','data/isolated/source_u0060.pt', '--run','v040_integration01',
           '--updates','1','--rollout-steps','128','--max-episode-steps','180',
           '--checkpoint-every','1','--eval-seeds','1','--eval-steps','180',
           '--epochs','1','--minibatch','64','--seed','20261011'])
    output=isolated/'v040_integration01_u0061.pt'
    report=isolated/'v040_integration01_u0061.json'
    assert output.exists() and report.exists()
    saved=torch.load(output,weights_only=True,map_location='cpu')
    assert saved['global_updates']==61
    assert saved['meta']['origin_stage']=='slater_v040'
    assert saved['meta']['full_report']['total_new_decisions']==128
    assert saved['meta']['full_report']['recent_updates'][0]['timeouts_bootstrapped']>0
    assert json.loads(report.read_text())['status']=='EXPERIMENT_ONLY_NOT_VALIDATED_RLBOT'
    assert source.read_bytes()==b'dummy checkpoint artifact'
    with pytest.raises(FileExistsError):
        m.run(['--from-checkpoint','data/isolated/source_u0060.pt', '--run','v040_integration01'])


def test_batched_script_skips_unused_nn_inference(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(m.prev, 'sample_nexto_action',
                        lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('NN should not run')))
    env=m.RivalEnv.__new__(m.RivalEnv)
    env.current_opponent='nexto_script'
    env.state=SimpleNamespace(ball=SimpleNamespace(position=np.array([0.,0.,92.])))
    env.t=0
    env.kickoff_ball_touched=False
    env.script_action_steps=0
    env.last_control_source=None
    command=env._opponent_commands('orange-0')
    expected=m.prev.grouped_control(0, enabled=True, active=True,
                                    nn_control=np.zeros(8,dtype=np.float32), action_repeat=8)
    np.testing.assert_array_equal(command,expected)
    assert env.script_action_steps==1 and env.last_control_source=='script'


def test_eval_modes_restrict_to_training():
    p=m.make_parser()
    ok=p.parse_args(['--run','v040_eval01','--eval-modes','nexto_script,frozen_u60'])
    assert m.validate_args(ok) == m.RIVALS
    bad=p.parse_args(['--run','v040_eval01','--eval-modes','not_a_rival'])
    with pytest.raises(ValueError):m.validate_args(bad)
    bad=p.parse_args(['--run','v040_eval01','--modes','nexto_script,frozen_u60',
                      '--eval-modes','nexto_greedy'])
    with pytest.raises(ValueError):m.validate_args(bad)


def test_pinned_original_v60_anchor_requires_hash_and_independent_parameters(tmp_path,monkeypatch):
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.l=torch.nn.Linear(4,4)
        def forward(self,x):
            return self.l(x)
    folder=tmp_path/'data'/'isolated'
    folder.mkdir(parents=True)
    path=folder/'original_u0060.pt'
    first=Toy()
    torch.save({'stage':'slater_v027', 'source_sha':'source_ok',
                'meta':{'nexto_sha':'nexto_ok'},'actor':first.state_dict()},path)
    actor=Toy()
    vendor=tmp_path/'vendor'/'nexto'
    vendor.mkdir(parents=True)
    (vendor/'nexto-model.pt').write_bytes(b'fake')
    with pytest.raises(RuntimeError, match='SHA mismatch'):
        m.load_original_v60_anchor(tmp_path,actor,checkpoint_arg='data/isolated/original_u0060.pt',
                                   source_sha='source_ok',nexto_sha='nexto_ok')
    prior_sha=m.base.sha256
    monkeypatch.setattr(m.base,'sha256',lambda p: m.EXPECTED_V60_SHA256 if Path(p)==path else prior_sha(p))
    monkeypatch.setattr(torch.jit,'load',lambda *args,**kwargs: Toy())
    loaded,digest=m.load_original_v60_anchor(tmp_path,actor,
        checkpoint_arg='data/isolated/original_u0060.pt',source_sha='source_ok',nexto_sha='nexto_ok')
    assert digest==m.EXPECTED_V60_SHA256
    assert m.params_unchanged(loaded,[x.detach().clone() for x in first.parameters()])
    assert not ({p.data_ptr() for p in actor.parameters()} &
                {p.data_ptr() for p in loaded.parameters()})
    with pytest.raises(ValueError,match='provenance'):
        m.load_original_v60_anchor(tmp_path,actor,
            checkpoint_arg='data/isolated/original_u0060.pt',source_sha='wrong',nexto_sha='nexto_ok')
    with pytest.raises(ValueError):
        m.load_original_v60_anchor(tmp_path,actor,checkpoint_arg='../../outside.pt',
                                   source_sha='source_ok',nexto_sha='nexto_ok')
