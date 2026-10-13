"""Actual attention actor and Python PPO reference fixture; no source edits."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from slater_ppo import trust_region_update
from slater_cycle9_native_ppo_v025 import gae
from slater_versatile_env import VersatileCritic


class Fixture(torch.nn.Module):
    def __init__(self, tensors):
        super().__init__()
        for name, value in tensors.items():
            self.register_buffer(name, value)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x


def generate(actor_path, inputs_path, out):
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.manual_seed(12007)
    actor = torch.jit.load(str(actor_path)).eval()
    teacher = torch.jit.load(str(actor_path)).eval()
    for p in actor.parameters(): p.requires_grad_(True)
    for p in teacher.parameters(): p.requires_grad_(False)
    critic = VersatileCritic()
    inputs = torch.jit.load(str(inputs_path))
    n = 8
    q, kv, mask = (getattr(inputs, name)[:n].clone() for name in ('q', 'kv', 'mask'))
    task = torch.arange(n) % 12
    with torch.no_grad():
        logits = actor((q, kv, mask))[0]
        action = (logits.argmax(-1) + 17) % 90
        old_logp = logits.log_softmax(-1).gather(1, action[:, None]).squeeze(1)
        value = critic.value_for_task((q, kv, mask), task)
    reward = torch.tensor([.3, -.1, 1., .8, -.25, 0., .5, -.7])
    done = torch.tensor([0., 0., 1., 0., 0., 1., 0., 0.])
    adv, ret = gae(reward.numpy(), value.numpy(), done.numpy(), .125)
    anchor_weight = torch.linspace(.01, .08, n)
    rows = {name: list(x.numpy()) for name, x in {'q': q, 'kv': kv, 'mask': mask,
        'action': action, 'old_logp': old_logp, 'value': value, 'reward': reward,
        'done': done, 'task': task, 'anchor_weight': anchor_weight}.items()}
    rows['adv'], rows['ret'] = adv, ret
    ao, co = torch.optim.Adam(actor.parameters(), lr=1e-5), torch.optim.Adam(critic.parameters(), lr=1e-4)
    tensors = dict(q=q, kv=kv, mask=mask, action=action, old_logp=old_logp,
        value=value, reward=reward, done=done, task=task, anchor_weight=anchor_weight,
        expected_logits=logits, expected_adv=torch.from_numpy(adv), expected_ret=torch.from_numpy(ret))
    for name, value in critic.state_dict().items():
        tensors['critic_' + name.replace('.', '_')] = value.clone()
    before = {k: v.clone() for k,v in actor.state_dict().items()}
    metrics = trust_region_update(actor, teacher, critic, ao, co, rows, 1, n, .03,
                                  seed=42, target_kl=.015, max_backtracks=3)
    with torch.no_grad():
        tensors['expected_after_logits'] = actor((q, kv, mask))[0]
        tensors['expected_after_values'] = critic.value_for_task((q, kv, mask), task)
    torch.jit.script(Fixture(tensors)).save(str(out / 'fixture.pt'))
    torch.jit.save(actor, str(out / 'python_actor_after.pt'))
    (out / 'python_metrics.json').write_text(json.dumps(metrics, indent=2))
    (out / 'source.json').write_text(json.dumps({'actor': str(actor_path), 'inputs': str(inputs_path),
        'changed_actor_tensors': sum(not torch.equal(before[k], v) for k,v in actor.state_dict().items())}, indent=2))
    print(json.dumps(metrics))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('actor', type=Path); p.add_argument('inputs', type=Path); p.add_argument('out', type=Path)
    a=p.parse_args(); generate(a.actor, a.inputs, a.out)
