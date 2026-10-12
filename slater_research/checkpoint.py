"""Cycle9 SHA-guarded loader and conservative PPO regularization helpers."""
from __future__ import annotations
import hashlib
from pathlib import Path
import torch
import torch.nn.functional as F

CYCLE9_SHA='50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
CHAMPION_SHA='c9596e2945ca6997f9ed496d90e89a772e519e4377db9989ef0645f827f6501a'
CYCLE9=Path('data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt')


def verify_sha(path,expected=CYCLE9_SHA):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    actual=h.hexdigest()
    if actual!=expected:raise RuntimeError(f'{path}: SHA mismatch {actual} != {expected}')
    return actual


def cycle9_pair(project_root):
    """Return independent student/teacher TorchScript modules with identical weights."""
    root=Path(project_root)
    ckpt=root/CYCLE9
    verify_sha(ckpt, CYCLE9_SHA)
    source=root/'vendor/nexto/nexto-model.pt'
    payload=torch.load(str(ckpt),map_location='cpu',weights_only=True)
    if not isinstance(payload,dict) or 'actor' not in payload:
        raise TypeError('Expected checkpoint dictionary with actor state_dict')
    actor=torch.jit.load(str(source),map_location='cpu')
    actor.load_state_dict(payload['actor'],strict=True)
    # TorchScript cloning via deepcopy() can produce tensors that are not leaf
    # variables in some PyTorch versions. Load an independent teacher instead.
    # The teacher is NEVER included in an optimizer and every teacher forward
    # pass is performed inside torch.no_grad(), so no teacher graph is built.
    teacher=torch.jit.load(str(source),map_location='cpu')
    teacher.load_state_dict(payload['actor'],strict=True)
    teacher.eval()
    actor.eval()  # Preserve the original Nexto scripted-forward convention.
    return actor,teacher


def stable_kl(student_logits,teacher_logits,temperature=1.5):
    """D_KL(teacher || student), with temperature squared."""
    t=temperature
    return F.kl_div(F.log_softmax(student_logits/t,dim=-1),
                    F.softmax(teacher_logits.detach()/t,dim=-1),
                    reduction='batchmean')*t*t


def guarded_ppo_loss(student_logits,teacher_logits,actions,old_logp,advantage,
                     clip=.15,teacher_weight=.08,entropy_weight=.005):
    from torch.distributions import Categorical
    dist=Categorical(logits=student_logits)
    ratio=torch.exp(dist.log_prob(actions)-old_logp)
    surrogate=torch.minimum(ratio*advantage,
                            torch.clamp(ratio,1.-clip,1.+clip)*advantage)
    return (-surrogate.mean() + teacher_weight*stable_kl(student_logits,teacher_logits)
            -entropy_weight*dist.entropy().mean())


def save_candidate_atomic(target, actor, critic, optimizer, data):
    """Create isolated atomic snapshot; NEVER replace Cycle9/champion."""
    path=Path(target)
    if path.exists():raise FileExistsError(f'Refusing to replace existing candidate: {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.name in ('champion.pt',CYCLE9.name):raise ValueError('Protected checkpoint name')
    payload=dict(actor=actor.state_dict(),critic=critic.state_dict(),
                 optimizer=optimizer.state_dict(),source_sha=CYCLE9_SHA,meta=data)
    tmp=path.with_name(path.name+'.partial')
    torch.save(payload,tmp)
    tmp.replace(path)
