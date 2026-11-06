"""Chronos-initialized actor, native-timed 1v1 environment, and anchored PPO.

The actor keeps the deployed 225 -> shared 960x960 -> policy 960/800/640/640 -> 90
network. The extra 90 training observation entries are the decision-time mask,
not extra inputs to the pretrained actor. No NovaForge-276 conversion is involved.
"""
from __future__ import annotations

import hashlib
import copy
from pathlib import Path

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import torch
from torch import nn
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.utils import explained_variance

from .core import check_model
from .environment import ArenaEnv
from .giga_teachers import GigaNetwork,GigaTeacher,TABLE,build_features,native_action_mask

CHRONOS_CONTRACT=dict(name='novaforge-chronos-1v1-v1',observation=225,training_observation=315,
    actions=90,action_sha256=hashlib.sha256(TABLE.tobytes()).hexdigest(),tick_skip=8,
    planned_action_delay_ticks=7,simulator_action_delay_ticks=1,mirror='chronos-own-positive-x',
    boost_timer_order='pinned-chronos-deployed')


class ChronosSnapshot(GigaTeacher):
    def __init__(self,path):
        check_model(path,CHRONOS_CONTRACT)
        self.kind='chronos';self.forecast=None
        self.network=torch.jit.load(str(path),map_location='cpu').eval()
        for parameter in self.network.parameters():parameter.requires_grad_(False)


class ChronosArena(ArenaEnv):
    """Goal reward plus discount-consistent potential shaping; no flat touch farming."""
    def __init__(self,*args,**kwargs):
        from .objectives import objective
        self.objective=objective(args[0] if args else kwargs['config'])
        super().__init__(*args,**kwargs)

    def potential(self,state):
        direction=1 if self.team==0 else -1
        distance=min(float(np.linalg.norm(state.ball.position-state.cars[self.agent].physics.position)),12000.)
        return self.objective['field']*direction*float(state.ball.position[1])/5120-self.objective['distance']*distance/6000

    def _reward(self,old,new,outcome,terminated):
        if self.cfg.get('chronos',{}).get('reward_profile')=='potential_goal_v2':
            self.last_reward_parts={}
            return 0. # Account once at the eight-tick decision boundary below.
        gamma4=self.cfg['ppo']['gamma']**.5
        potential=gamma4*(0. if terminated else self.potential(new))-self.potential(old)
        self.last_reward_parts={'goal':10.*outcome}
        if self.cfg['rewards']!='sparse':self.last_reward_parts['potential']=potential
        for key,value in self.last_reward_parts.items():self.reward_parts[key]=self.reward_parts.get(key,0.)+value
        return float(sum(self.last_reward_parts.values()))

    def _truncated(self):
        # A PPO transition is eight ticks. Time-limit bootstrapping must never
        # observe a half decision; goals still terminate immediately.
        return self.steps%2==0 and super()._truncated()


class ChronosEnv(gym.Env):
    """An eight-tick learner decision executes seven held ticks then one new tick."""
    metadata={'render_modes':[]}
    def __init__(self,cfg,league_manifest=None,opponent=None,snapshot=None,scenario=None,side=None):
        self.arena=ChronosArena(cfg,league_manifest,opponent,snapshot,scenario,side,snapshot_kind='chronos_snapshot')
        self.action_space=spaces.Discrete(90)
        self.observation_space=spaces.Box(-np.inf,np.inf,(315,),np.float32)
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32)

    def observation(self):
        x,self.mirror=build_features(self.arena.state,self.arena.agent,self.previous,self.np_random,'chronos')
        mask=native_action_mask(self.arena.state.cars[self.arena.agent])
        if not mask.any():raise ValueError('Chronos has no valid action')
        return np.concatenate((x,mask.astype(np.float32)))

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        _,info=self.arena.reset(seed=seed,options=options)
        self.previous[:]=0;self.held[:]=0
        self.decisions=0
        self.reward_total=0.;self.reward_parts={}
        return self.observation(),info

    def step(self,action):
        action=int(action)
        if not 0<=action<90 or not native_action_mask(self.arena.state.cars[self.arena.agent])[action]:
            raise ValueError('Invalid/masked Chronos action')
        planned=TABLE[action].copy()
        if self.mirror:planned[[1,3,4]]*=-1
        return self.step_world_controls(planned)

    def step_world_controls(self,planned):
        planned=np.asarray(planned,dtype=np.float32)
        if planned.shape!=(8,) or not np.isfinite(planned).all() or abs(planned).max()>1.001:raise ValueError('Invalid expert controls')
        commands=np.repeat(self.held[None,:],8,axis=0);commands[7]=planned
        self.previous=planned.copy()
        initial_potential=self.arena.potential(self.arena.state)
        reward=0.
        for start in (0,4):
            _,part,terminated,truncated,info=self.arena.step_controls(commands[start:start+4])
            discount=1. if start==0 else self.arena.cfg['ppo']['gamma']**.5
            reward+=discount*part
            for key,value in self.arena.last_reward_parts.items():
                self.reward_parts[key]=self.reward_parts.get(key,0.)+discount*value
            if terminated or truncated:break
        self.held=planned.copy()
        if self.arena.cfg.get('chronos',{}).get('reward_profile')=='potential_goal_v2':
            parts={'goal':self.arena.objective['goal']*info.get('outcome',0)}
            if self.arena.cfg['rewards']!='sparse':
                parts['potential']=(self.arena.cfg['ppo']['gamma']*(0. if terminated else self.arena.potential(self.arena.state))
                                    -initial_potential)
            reward=float(sum(parts.values()))
            for key,value in parts.items():self.reward_parts[key]=self.reward_parts.get(key,0.)+value
        self.decisions+=1
        self.reward_total+=reward
        if 'episode' in info:
            info['episode']={'r':self.reward_total,'l':self.decisions}
            info['reward_parts']=dict(self.reward_parts)
        return self.observation(),float(reward),terminated,truncated,info

    def close(self):self.arena.close()


class ChronosPolicy(ActorCriticPolicy):
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('net_arch',[]);kwargs.setdefault('ortho_init',False)
        super().__init__(*args,**kwargs)

    def _build(self,lr_schedule):
        self.actor=GigaNetwork(None,'chronos').requires_grad_(True)
        self.anchor=GigaNetwork(None,'chronos').requires_grad_(False)
        self.value_net=nn.Sequential(nn.Linear(225,256),nn.Tanh(),nn.Linear(256,256),nn.Tanh(),nn.Linear(256,1))
        self.optimizer=self.optimizer_class([
            {'params':self.actor.parameters()}, {'params':self.value_net.parameters()}],
            lr=lr_schedule(1),**self.optimizer_kwargs)

    @staticmethod
    def masked(logits,obs):
        mask=obs[:,225:]>0
        if not torch.all(mask.any(dim=-1)):raise ValueError('Empty Chronos action mask')
        return torch.where(mask,logits,torch.full_like(logits,-1e9))

    def logits(self,obs):return self.masked(self.actor(obs[:,:225]),obs)

    def get_distribution(self,obs):
        return self.action_dist.proba_distribution(action_logits=self.logits(obs))

    def _predict(self,obs,deterministic=False):return self.get_distribution(obs).get_actions(deterministic=deterministic)

    def forward(self,obs,deterministic=False):
        dist=self.get_distribution(obs);actions=dist.get_actions(deterministic=deterministic)
        return actions,self.predict_values(obs),dist.log_prob(actions)

    def evaluate_actions(self,obs,actions):
        dist=self.get_distribution(obs)
        return self.predict_values(obs),dist.log_prob(actions),dist.entropy()

    def predict_values(self,obs):return self.value_net(obs[:,:225])

    def anchor_kl(self,obs,current_log_probs=None):
        current=torch.log_softmax(self.logits(obs),dim=-1) if current_log_probs is None else current_log_probs
        with torch.no_grad():
            reference=torch.log_softmax(self.masked(self.anchor(obs[:,:225]),obs),dim=-1)
        return (reference.exp()*(reference-current)).sum(-1).mean()

    def set_training_mode(self,mode):
        super().set_training_mode(mode);self.anchor.eval()


class ChronosPPO(PPO):
    """SB3 rollout/GAE/checkpoint machinery, with separate rates and frozen-actor KL.

    The clipped objective follows SB3 PPO (MIT), with credit in THIRD_PARTY.md.
    Two critic-only rollout updates precede actor updates by default.
    """
    def __init__(self,*args,actor_lr=1e-5,critic_lr=3e-4,anchor_coef=.1,critic_warmup_updates=2,**kwargs):
        self.actor_lr=actor_lr;self.critic_lr=critic_lr;self.anchor_coef=anchor_coef
        self.critic_warmup_updates=critic_warmup_updates;self.chronos_updates=0
        super().__init__(*args,**kwargs)

    def train(self):
        policy_before=copy.deepcopy(self.policy.state_dict())
        optimizer_before=copy.deepcopy(self.policy.optimizer.state_dict())
        try:
            self._train_chronos()
            probe=torch.as_tensor(self.rollout_buffer.observations.reshape(-1,self.observation_space.shape[0])[:512],device=self.device)
            with torch.no_grad():anchor_kl=float(self.policy.anchor_kl(probe))
            if not np.isfinite(anchor_kl):raise FloatingPointError('Nonfinite anchor KL')
            if anchor_kl>getattr(self,'anchor_kl_limit',float('inf')):
                self.policy.load_state_dict(policy_before);self.policy.optimizer.load_state_dict(optimizer_before)
                self.actor_lr=max(self.actor_lr*.5,1e-7);self.anchor_coef=min(self.anchor_coef*1.5,4.)
                self.logger.record('train/update_rejected',1)
                self.consecutive_rejections=getattr(self,'consecutive_rejections',0)+1
                if self.consecutive_rejections>=3:self.training_halt_reason='Three consecutive updates exceeded the frozen-policy KL limit'
            else:
                self.consecutive_rejections=0
                self.logger.record('train/update_rejected',0)
            self.logger.record('train/anchor_probe_kl',anchor_kl)
        except (FloatingPointError,ValueError,RuntimeError):
            self.policy.load_state_dict(policy_before);self.policy.optimizer.load_state_dict(optimizer_before)
            raise

    def _train_chronos(self):
        policy=self.policy;policy.set_training_mode(True)
        policy.optimizer.param_groups[0]['lr']=self.actor_lr
        policy.optimizer.param_groups[1]['lr']=self.critic_lr
        warmup=self.chronos_updates<self.critic_warmup_updates
        clip=self.clip_range(self._current_progress_remaining)
        logs={key:[] for key in ('loss','policy_gradient_loss','value_loss','entropy_loss','anchor_kl','approx_kl','clip_fraction')}
        keep_going=True
        for _ in range(self.n_epochs):
            for data in self.rollout_buffer.get(self.batch_size):
                actions=data.actions.long().flatten()
                values,logp,entropy=policy.evaluate_actions(data.observations,actions)
                advantages=data.advantages
                if self.normalize_advantage and len(advantages)>1:
                    advantages=(advantages-advantages.mean())/(advantages.std()+1e-8)
                ratio=torch.exp(logp-data.old_log_prob)
                actor_loss=-torch.minimum(advantages*ratio,advantages*torch.clamp(ratio,1-clip,1+clip)).mean()
                value_loss=nn.functional.mse_loss(values.flatten(),data.returns)
                entropy_loss=-entropy.mean()
                anchor_loss=policy.anchor_kl(data.observations,policy.action_dist.distribution.logits)
                with torch.no_grad():
                    delta=logp-data.old_log_prob
                    approx=((delta.exp()-1)-delta).mean().item()
                if not warmup and self.target_kl is not None and approx>1.5*self.target_kl:
                    keep_going=False;break
                loss=self.vf_coef*value_loss
                if not warmup:loss=loss+actor_loss+self.ent_coef*entropy_loss+self.anchor_coef*anchor_loss
                if not torch.isfinite(loss):raise FloatingPointError('Nonfinite Chronos PPO loss')
                policy.optimizer.zero_grad(set_to_none=True);loss.backward()
                nn.utils.clip_grad_norm_(policy.value_net.parameters(),self.max_grad_norm,error_if_nonfinite=True)
                if not warmup:nn.utils.clip_grad_norm_(policy.actor.parameters(),self.max_grad_norm,error_if_nonfinite=True)
                policy.optimizer.step()
                for key,value in [('loss',loss.item()),('policy_gradient_loss',actor_loss.item()),('value_loss',value_loss.item()),
                    ('entropy_loss',entropy_loss.item()),('anchor_kl',anchor_loss.item()),('approx_kl',approx),
                    ('clip_fraction',(torch.abs(ratio-1)>clip).float().mean().item())]:logs[key].append(value)
            self._n_updates+=1
            if not keep_going:break
        self.chronos_updates+=1
        for key,values in logs.items():
            if values:self.logger.record('train/'+key,float(np.mean(values)))
        self.logger.record('train/critic_warmup',int(warmup))
        self.logger.record('train/actor_lr',self.actor_lr);self.logger.record('train/critic_lr',self.critic_lr)
        self.logger.record('train/n_updates',self._n_updates)
        self.logger.record('train/chronos_updates',self.chronos_updates)
        self.logger.record('train/explained_variance',explained_variance(self.rollout_buffer.values.flatten(),self.rollout_buffer.returns.flatten()))
