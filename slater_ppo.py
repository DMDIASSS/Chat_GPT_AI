"""Bound native PPO policy drift on the states actually collected for an update."""
from __future__ import annotations

import copy
import math

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base


def rollout_log_probs(actor, rows, minibatch, device):
    parts = []
    with torch.no_grad():
        for start in range(0, len(rows['action']), minibatch):
            x = tuple(torch.as_tensor(np.stack(rows[k][start:start + minibatch]),
                                      dtype=torch.float32, device=device)
                      for k in ('q', 'kv', 'mask'))
            parts.append(base.logits_of(actor, x).log_softmax(-1))
    return torch.cat(parts)


def trust_region_update(actor, teacher, critic, actor_opt, critic_opt, rows,
                        epochs, minibatch, teacher_weight, seed, device='cpu',
                        *, target_kl=.02):
    """Rollback an epoch exceeding exact KL(old rollout policy || new policy).

    Adam moments are restored along with actor weights; the critic may keep its
    valid supervised updates. This bound applies to sampled rollout states,
    not every possible game state. Teacher KL remains a separate anchor loss.
    """
    if not math.isfinite(target_kl) or target_kl <= 0:
        raise ValueError('target_kl must be finite and positive')
    if epochs < 1 or minibatch < 1 or not rows['action']:
        raise ValueError('Nonempty rollout, positive epochs and minibatch required')
    old_logp = rollout_log_probs(actor, rows, minibatch, device)
    old_prob = old_logp.exp()
    accepted = []
    last_kl = 0.
    rejected_kl = None
    for epoch in range(epochs):
        weights = {k: v.detach().clone() for k, v in actor.state_dict().items()}
        optimizer = copy.deepcopy(actor_opt.state_dict())
        try:
            metrics = base.update(actor, teacher, critic, actor_opt, critic_opt,
                                  rows, 1, minibatch, teacher_weight, seed + epoch, device)
            new_logp = rollout_log_probs(actor, rows, minibatch, device)
            drift = float((old_prob * (old_logp - new_logp)).sum(-1).mean().item())
            if not math.isfinite(drift):
                raise FloatingPointError('Nonfinite policy drift')
        except Exception:
            actor.load_state_dict(weights)
            actor_opt.load_state_dict(optimizer)
            actor_opt.zero_grad(set_to_none=True)
            raise
        if drift > target_kl:
            actor.load_state_dict(weights)
            actor_opt.load_state_dict(optimizer)
            actor_opt.zero_grad(set_to_none=True)
            rejected_kl = drift
            break
        last_kl = max(0., drift)  # roundoff can make a zero KL slightly negative
        accepted.append(metrics)
    result = {k: float(np.mean([m[k] for m in accepted])) for k in accepted[0]} if accepted else {}
    result.update(rollout_policy_kl=last_kl, target_kl=target_kl,
                  accepted_actor_epochs=len(accepted), attempted_epochs=epoch + 1,
                  actor_epoch_rolled_back=rejected_kl is not None,
                  rejected_policy_kl=rejected_kl)
    return result
