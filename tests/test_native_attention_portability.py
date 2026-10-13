"""CPU portability of native actors whose TorchScript graph names CUDA."""
from pathlib import Path

import pytest
import torch

import slater_cycle9_native_ppo_v025 as base
from slater_v041_core import sha256
from slater_v041_worker import model_from_checkpoint


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/nexto/nexto-model.pt'


def _device_nodes(block):
    for node in block.nodes():
        if node.kind() == 'prim::Constant' and str(node.output().type()) == 'Device':
            yield node
        for child in node.blocks():
            yield from _device_nodes(child)


def _replace_script_devices(actor, value):
    count = 0
    for module in actor.modules():
        for method in module._c._method_names():
            for node in _device_nodes(module._c._get_method(method).graph):
                node.s_('value', value)
                count += 1
    assert count > 0, 'The fixture must exercise an actual embedded device constant'


def test_cuda_graph_actor_loads_on_cpu_with_identical_weights_and_actions(tmp_path):
    torch.set_num_threads(1)
    original_sha = sha256(VENDOR)
    original = torch.jit.load(str(VENDOR), map_location='cpu').eval()
    expected_weights = {name: value.clone() for name, value in original.state_dict().items()}
    # Give the checkpoint real changed weights so a fallback to untrained Nexto
    # would fail. Only its graph device constant is CUDA; no GPU is needed.
    first = next(iter(expected_weights))
    expected_weights[first].reshape(-1)[0] += .125
    reference = torch.jit.load(str(VENDOR), map_location='cpu').eval()
    reference.load_state_dict(expected_weights, strict=True)
    original.load_state_dict(expected_weights, strict=True)
    _replace_script_devices(original, 'cuda:0')
    checkpoint = tmp_path / 'actor.pt'
    torch.jit.save(original, str(checkpoint))
    checkpoint_sha = sha256(checkpoint)
    stored = torch.jit.load(str(checkpoint), map_location='cpu')
    assert any(node.s('value') == 'cuda:0' for module in stored.modules()
               for method in module._c._method_names()
               for node in _device_nodes(module._c._get_method(method).graph))
    restored = model_from_checkpoint(checkpoint, VENDOR)
    assert len(restored.state_dict()) == 44
    assert all(torch.equal(value, restored.state_dict()[name]) for name, value in expected_weights.items())
    generator = torch.Generator().manual_seed(27)
    for tokens in (37, 41):
        inputs = (torch.randn(4, 1, 32, generator=generator),
                  torch.randn(4, tokens, 24, generator=generator), torch.zeros(4, tokens))
        inputs[2][:, -3:] = -10000
        with torch.no_grad():
            wanted = base.logits_of(reference, inputs)
            actual = base.logits_of(restored, inputs)
        assert torch.equal(actual, wanted)
        assert torch.equal(actual.argmax(-1), wanted.argmax(-1))
    assert sha256(checkpoint) == checkpoint_sha and sha256(VENDOR) == original_sha


def test_full_ppo_checkpoint_remains_supported_without_relaxing_architecture(tmp_path):
    actor = torch.jit.load(str(VENDOR), map_location='cpu')
    weights = {name: value.clone() for name, value in actor.state_dict().items()}
    next(iter(weights.values())).reshape(-1)[0] += .25
    checkpoint = tmp_path / 'full_ppo.pt'
    torch.save({'actor': weights, 'actor_optimizer': {'state': {}}, 'updates': 278}, checkpoint)
    restored = model_from_checkpoint(checkpoint, VENDOR)
    assert all(torch.equal(value, restored.state_dict()[name]) for name, value in weights.items())
    weights[next(iter(weights))] = torch.full_like(next(iter(weights.values())), float('nan'))
    bad = tmp_path / 'nonfinite.pt'
    torch.save({'actor': weights}, bad)
    with pytest.raises(ValueError, match='nonfinite attention tensor'):
        model_from_checkpoint(bad, VENDOR)


def test_unverified_vendor_and_incompatible_script_are_rejected(tmp_path):
    modified_vendor = tmp_path / 'modified_vendor.pt'
    modified_vendor.write_bytes(VENDOR.read_bytes() + b'changed')
    with pytest.raises(RuntimeError, match='Original Nexto changed'):
        model_from_checkpoint(VENDOR, modified_vendor)
    unrelated = torch.jit.trace(torch.nn.Linear(32, 90), torch.zeros(1, 32))
    checkpoint = tmp_path / 'unrelated.pt'
    torch.jit.save(unrelated, str(checkpoint))
    with pytest.raises(ValueError, match='44-tensor attention architecture'):
        model_from_checkpoint(checkpoint, VENDOR)
