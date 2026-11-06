"""Two independent direct policies; privileged information never enters an actor.

The small, zero-initialized public-context residual preserves the initial native
logits exactly. Both the original trunk and the residual are trainable. The
private nine numbers describe an already queued opponent command, not a future
simulation or the learner's action. All clocks use the native 7+1 tick delay.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import torch
from torch import nn
from stable_baselines3.common.policies import ActorCriticPolicy

from .chronos import ChronosPPO
from .core import check_model, write_model_meta
from .giga_teachers import GigaNetwork, GigaTeacher, BallForecast, TABLE, build_features, native_action_mask
from .models import _sync_serialized_file

FAMILIES=('chronos','galactus')
CORE={'chronos':225,'galactus':258}


def contract(family):
    return dict(name='forgeleague-direct-v1',family=family,core=CORE[family],actor_input=CORE[family]+3,
        training_input=CORE[family]+3+90+9,actions=90,action_sha256=hashlib.sha256(TABLE.tobytes()).hexdigest(),
        hitbox='octane',public_context=['clipped_score_difference/5','remaining_seconds/300','centered_stationary_ball'],
        critic_private=['queued_world_controls_8','ticks_until_application/8'],tick_skip=8,planned_delay_ticks=7,
        simulator_delay_ticks=1,scope='1v1')


def context(state,agent,score,remaining):
    centered=np.linalg.norm(state.ball.position[:2])<5 and np.linalg.norm(state.ball.linear_velocity)<10
    return np.array([np.clip(score/5,-1,1),np.clip(remaining/300,0,2),float(centered)],dtype=np.float32)


class DirectActor(nn.Module):
    def __init__(self,family):
        super().__init__()
        self.core_size=CORE[family]
        self.core=GigaNetwork(None,family).requires_grad_(True)
        self.residual=nn.Sequential(nn.Linear(self.core_size+3,64),nn.Tanh(),nn.Linear(64,90))
        nn.init.zeros_(self.residual[-1].weight);nn.init.zeros_(self.residual[-1].bias)

    def forward(self,x):
        return self.core(x[:,:self.core_size])+torch.tanh(self.residual(x))


class DirectPolicy(ActorCriticPolicy):
    def __init__(self,*args,family='chronos',privileged=False,**kwargs):
        self.family=family;self.privileged=privileged;self.actor_size=CORE[family]+3
        kwargs.setdefault('net_arch',[]);kwargs.setdefault('ortho_init',False)
        super().__init__(*args,**kwargs)

    def _get_constructor_parameters(self):
        return dict(super()._get_constructor_parameters(),family=self.family,privileged=self.privileged)

    def _build(self,lr_schedule):
        self.actor=DirectActor(self.family)
        self.anchor=copy.deepcopy(self.actor).requires_grad_(False)
        self.value_net=nn.Sequential(nn.Linear(self.actor_size+9,256),nn.Tanh(),nn.Linear(256,256),nn.Tanh(),nn.Linear(256,1))
        self.optimizer=self.optimizer_class([{'params':self.actor.parameters()},{'params':self.value_net.parameters()}],
            lr=lr_schedule(1),**self.optimizer_kwargs)

    def masked(self,logits,obs):
        mask=obs[:,self.actor_size:self.actor_size+90]>0
        if not torch.all(mask.any(-1)):raise ValueError('Empty direct-policy action mask')
        return torch.where(mask,logits,torch.full_like(logits,-1e9))

    def logits(self,obs):return self.masked(self.actor(obs[:,:self.actor_size]),obs)
    def get_distribution(self,obs):return self.action_dist.proba_distribution(action_logits=self.logits(obs))
    def _predict(self,obs,deterministic=False):return self.get_distribution(obs).get_actions(deterministic=deterministic)
    def predict_values(self,obs):
        private=obs[:,-9:] if self.privileged else torch.zeros_like(obs[:,-9:])
        return self.value_net(torch.cat((obs[:,:self.actor_size],private),dim=-1))
    def forward(self,obs,deterministic=False):
        dist=self.get_distribution(obs);action=dist.get_actions(deterministic=deterministic)
        return action,self.predict_values(obs),dist.log_prob(action)
    def evaluate_actions(self,obs,actions):
        dist=self.get_distribution(obs)
        return self.predict_values(obs),dist.log_prob(actions),dist.entropy()
    def anchor_kl(self,obs,current_log_probs=None):
        current=torch.log_softmax(self.logits(obs),-1) if current_log_probs is None else current_log_probs
        with torch.no_grad():reference=torch.log_softmax(self.masked(self.anchor(obs[:,:self.actor_size]),obs),-1)
        return (reference.exp()*(reference-current)).sum(-1).mean()
    def set_training_mode(self,mode):
        super().set_training_mode(mode);self.anchor.eval()


def new_model(cfg,env,family,privileged,initial_actor):
    model=ChronosPPO(DirectPolicy,env,device=cfg['device'],seed=cfg['seed'],verbose=0,
        policy_kwargs=dict(family=family,privileged=privileged),actor_lr=cfg['actor_lr'],critic_lr=cfg['critic_lr'],
        anchor_coef=cfg['anchor_coef'],critic_warmup_updates=cfg['warmup_rollouts'],**cfg['ppo'])
    initial=torch.jit.load(str(initial_actor),map_location='cpu')
    model.policy.actor.load_state_dict(initial.state_dict(),strict=True)
    model.policy.anchor.load_state_dict(initial.state_dict(),strict=True)
    with torch.no_grad():model.policy.value_net[-1].weight.zero_();model.policy.value_net[-1].bias.zero_()
    model.anchor_kl_limit=cfg['anchor_kl_limit']
    return model


def save_actor(actor,path,family,**meta):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    actor=copy.deepcopy(actor).cpu().eval().requires_grad_(False)
    scripted=torch.jit.script(actor)
    x=torch.linspace(-1,1,2*(CORE[family]+3)).reshape(2,-1)
    with torch.inference_mode():torch.testing.assert_close(scripted(x),actor(x),rtol=0,atol=0)
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.lt');os.close(fd)
    try:
        torch.jit.save(scripted,temp);_sync_serialized_file(temp);os.replace(temp,path)
        write_model_meta(path,contract=contract(family),**meta)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path


class DirectController(GigaTeacher):
    """Frozen exported actor, deterministic native clock, public score/time only."""
    def __init__(self,path):
        meta=json.loads(Path(str(path)+'.json').read_text());self.kind=meta['contract']['family'];check_model(path,contract(self.kind))
        from .inference import frozen_inference
        self.network=frozen_inference(torch.jit.load(str(path),map_location='cpu'))
        if self.kind=='galactus':
            # Live exports have no training arena to initialize RocketSim's
            # meshes. Resolve the meshes shipped by the installed RLGym wheel.
            import rlgym.rocket_league.sim as sim
            import RocketSim as rs
            try:rs.init(str(Path(sim.__file__).parent/'collision_meshes'))
            except RuntimeError as error:
                if str(error)!='Already inited':raise
        self.forecast=BallForecast() if self.kind=='galactus' else None
        self.score=0;self.remaining=300.
    def set_context(self,score,remaining):self.score=score;self.remaining=remaining
    def controls_for_ticks(self,state,ticks=2):
        if ticks not in (2,4):raise ValueError('Expected two/four ticks')
        tick=int(state.tick_count-self.origin)
        if tick%2 or tick==self.last_call:raise ValueError('Duplicate or misaligned controller frame')
        self.last_call=tick
        if tick%8==0:
            pred=self.forecast.samples(state) if self.forecast else None
            obs,mirror=build_features(state,self.agent,self.obs_previous,self.rng,self.kind,pred)
            x=np.concatenate((obs,context(state,self.agent,self.score,self.remaining)))
            with torch.inference_mode():logits=self.network(torch.from_numpy(x)[None,:])[0].numpy()
            if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid direct actor output')
            mask=native_action_mask(state.cars[self.agent])
            planned=TABLE[int(np.where(mask,logits,-np.inf).argmax())].copy()
            if mirror:planned[[1,3,4]]*=-1
            self.obs_previous=planned.copy();self.pending=(tick+7,planned)
        result=np.repeat(self.held[None,:],ticks,axis=0)
        if self.pending is not None:
            due,command=self.pending
            if due<tick+ticks:
                result[max(0,due-tick):]=command;self.held=command.copy();self.pending=None
        return result
