"""Two-tick kickoff controls and an initialized-to-zero residual action head.

The original 90-action Nexto head remains untouched; the residual head makes
small precise analog adjustments. It is a TRAINABLE module; it doesn't create
speedflips without high-frequency teacher traces + RL supervision.
"""
import torch
from torch import nn
import numpy as np


class KickoffPrecisionHead(nn.Module):
    def __init__(self):
        super().__init__()
        # 32 self features, 24 pooled entities, 24 ball features, and elapsed time.
        self.net=nn.Sequential(nn.Linear(81,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh(),nn.Linear(128,8))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self,q,kv,mask,elapsed):
        valid=(1-mask).unsqueeze(-1).clamp(0,1)
        pooled=(kv*valid).sum(1)/valid.sum(1).clamp_min(1)
        ballidx=kv[:,:,3].argmax(1)
        ball=kv[torch.arange(kv.size(0),device=kv.device),ballidx]
        features=torch.cat((q[:,0],pooled,ball,elapsed.reshape(-1,1)),dim=-1)
        return torch.tanh(self.net(features))


def compose_controls(base_action,delta,residual_scale=.35):
    """Do not alter boost/jump gates unless independently supervised.

    Action order: throttle,steer,pitch,yaw,roll,jump,boost,handbrake.
    """
    a=np.asarray(base_action,dtype=np.float32).copy()
    d=np.asarray(delta,dtype=np.float32)
    if a.shape!=(8,) or d.shape!=(8,):raise ValueError('Expected 8 controls')
    a[:5]=np.clip(a[:5]+residual_scale*d[:5],-1,1)
    return a


def ticks_per_decision(kickoff,elapsed_seconds):
    """A policy decision every 2*8.33ms during early kickoff."""
    return 2 if kickoff and elapsed_seconds<1.4 else 8


def repeat_controls(action,active_ticks):
    if active_ticks not in (1,2,4,8):raise ValueError('Unsupported decision tick count')
    return np.repeat(np.asarray(action,dtype=np.float32).reshape(1,8),active_ticks,axis=0)
