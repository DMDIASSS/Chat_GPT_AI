from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .core import OBS_SIZE, ACTIONS, check_model, write_model_meta


class Actor(nn.Module):
    def __init__(self,policy):
        super().__init__()
        self.network=nn.Sequential(copy.deepcopy(policy.mlp_extractor.policy_net),
                                   copy.deepcopy(policy.action_net)).cpu().eval()

    def forward(self,obs):
        return self.network(obs)


def _sync_serialized_file(path):
    # Windows fsync needs a writable descriptor; r+b preserves the saved bytes.
    with open(path,'r+b') as f:
        f.flush()
        os.fsync(f.fileno())


def save_ppo(model,path,**meta):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='checkpoint_',suffix='.zip',dir=path.parent)
    os.close(fd)
    try:
        model.save(temp)
        _sync_serialized_file(temp)
        os.replace(temp,path)
        write_model_meta(path,timesteps=int(model.num_timesteps),**meta)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def export_actor(model,path,**meta):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    actor=Actor(model.policy)
    traced=torch.jit.trace(actor,torch.zeros(1,OBS_SIZE))
    example=traced(torch.zeros(2,OBS_SIZE))
    if example.shape!=(2,len(ACTIONS)) or not torch.isfinite(example).all():
        raise ValueError('Invalid actor export')
    fd,temp=tempfile.mkstemp(prefix='actor_',suffix='.pt',dir=path.parent)
    os.close(fd)
    try:
        torch.jit.save(traced,temp)
        _sync_serialized_file(temp)
        os.replace(temp,path)
        write_model_meta(path,timesteps=int(model.num_timesteps),**meta)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def load_ppo(path,env=None,device='cpu'):
    from stable_baselines3 import PPO
    check_model(path)
    return PPO.load(path,env=env,device=device)


class FrozenActor:
    def __init__(self,path):
        check_model(path)
        self.model=torch.jit.load(str(path),map_location='cpu').eval()

    def action(self,observation):
        with torch.inference_mode():
            logits=self.model(torch.from_numpy(observation).reshape(1,-1))
        if logits.shape!=(1,len(ACTIONS)) or not torch.isfinite(logits).all():
            raise ValueError('Frozen policy returned invalid logits')
        return int(logits.argmax(-1).item())
