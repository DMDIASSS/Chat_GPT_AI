"""Real native weight transfer, critic warmup and optimizer resume."""
from pathlib import Path

import pytest
import torch

import slater_freestyle as freestyle


ROOT = Path(__file__).resolve().parents[1]


def weights(path):
    return {k: v.detach().clone() for k, v in torch.jit.load(str(path), map_location='cpu').named_parameters()}


def identical(left, right):
    return left.keys() == right.keys() and all(torch.equal(left[k], right[k]) for k in left)


def test_real_actor_preservation_critic_warmup_and_post_warmup_learning(tmp_path, monkeypatch):
    build = ROOT / 'data/isolated/freestyle/build'
    if not freestyle.binary_path(build).is_file():
        pytest.skip('Optional native Freestyle build unavailable')
    freestyle.binary_identity(build)  # A stale binary must not pass this test.
    monkeypatch.setattr(freestyle, 'BASE', tmp_path)
    settings = freestyle.defaults()
    settings['native'].update(width=64, depth=1, games=2, steps_per_update=512, minibatch=256,
                              epochs=1, eval_every_updates=1, eval_episodes=2, device='cpu')
    settings['wandb']['mode'] = 'disabled'
    result = freestyle.train('parent', settings, build, updates=2)
    parent_path = Path(result['latest']['checkpoint'])
    before = {p.name: freestyle.sha256(p) for p in parent_path.iterdir() if p.is_file()}
    parent_actor = weights(parent_path / 'POLICY.lt')
    revised = freestyle.revised_reward_settings('parent')
    revised['native']['critic_warmup_updates'] = 2
    folder = freestyle.fork_policy('child', 'parent', revised, build)
    result = freestyle.train('child', revised, build, resume=True, updates=2)
    frozen = Path(result['latest']['checkpoint'])
    assert identical(parent_actor, weights(folder / 'checkpoints/0/POLICY.lt'))
    assert identical(parent_actor, weights(frozen / 'POLICY.lt'))
    assert not identical(weights(folder / 'checkpoints/0/CRITIC.lt'), weights(frozen / 'CRITIC.lt'))
    result = freestyle.train('child', revised, build, resume=True, updates=2)
    learned = Path(result['latest']['checkpoint'])
    assert not identical(parent_actor, weights(learned / 'POLICY.lt'))
    assert {p.name: freestyle.sha256(p) for p in parent_path.iterdir() if p.is_file()} == before
    saved = freestyle.read_json(learned / 'FREESTYLE_STATE.json')
    assert saved['initialization'] == 'POLICY_CONTINUATION'
    assert saved['parent_policy']['policy_sha256'] == before['POLICY.lt']
    assert saved['reward_version'] == 2 and result['updates'] == 4
