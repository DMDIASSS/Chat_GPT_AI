"""Timed, multi-goal 1v1; queued opponent action is exposed only to the critic."""
from __future__ import annotations

import copy
import gymnasium as gym
from gymnasium import spaces
import numpy as np

from .chronos import ChronosArena
from .core import ROOT
from .core import sha256
from .giga_teachers import BallForecast, TABLE, build_features, native_action_mask
from .teachers import make_opponent, controls_for_ticks
from .training import load_config
from .forge_models import CORE, DirectController, context

PROFILES={
    'balanced':{'kickoff':.5,'shot':.15,'defense':.15,'dribble':.075,'recovery':.075,'aerial':.025,'wall':.025},
    'pressure':{'kickoff':.25,'shot':.4,'dribble':.25,'wall':.1},
    'defense':{'kickoff':.25,'defense':.6,'recovery':.15},
    'recovery':{'kickoff':.25,'recovery':.35,'wall':.2,'aerial':.2},
    'match':{'kickoff':1.},
}


class PreparedOpponent:
    """Prepare before the learner chooses. Reuse those exact first two controls.

    There is no speculative step, second policy query, future action, or access
    to the learner's current sampled action. Control and privileged arms use the
    same preparation, seeds and clock. A command awaiting application is causal
    training information but is deliberately omitted from exported actors.
    """
    def __init__(self,base):self.base=base;self.cached=None
    def reset(self,state,agent,rng):self.base.reset(state,agent,rng);self.cached=None
    def prepare(self,state):
        if self.cached is None:self.cached=(int(state.tick_count),controls_for_ticks(self.base,state,2))
        if self.cached[0]!=int(state.tick_count):raise RuntimeError('Unconsumed prepared opponent frame')
        pending=getattr(self.base,'pending',None)
        if pending is None:return np.concatenate((self.cached[1][-1],[0])).astype(np.float32)
        due,command=pending
        tick=int(state.tick_count-self.base.origin)
        return np.concatenate((command,[np.clip((due-tick)/8,0,1)])).astype(np.float32)
    def controls_for_ticks(self,state,ticks=2):
        if self.cached is None:return controls_for_ticks(self.base,state,ticks)
        if ticks!=2 or self.cached[0]!=int(state.tick_count):raise RuntimeError('Prepared opponent timing mismatch')
        result=self.cached[1];self.cached=None
        return result


class ForgeArena(ChronosArena):
    def _choose_opponent(self,_snapshot_retries=0):
        entry=self.entry;key=(entry['name'],entry.get('sha256'))
        self.cfg['env']['opponent_hitbox']=entry.get('hitbox','breakout' if entry['name']=='chronos' else 'octane')
        if key not in self.cache:
            if entry.get('path') and sha256(entry['path'])!=entry['sha256']:raise ValueError('Frozen opponent changed')
            base=DirectController(entry['path']) if entry.get('path') else make_opponent(entry['name'])
            self.cache[key]=PreparedOpponent(base)
            for k in list(self.cache)[:-3]:self.cache.pop(k)
        self.opponent=self.cache[key];self.opponent_label=entry['name']
    def _reward(self,*args):self.last_reward_parts={};return 0.
    def _truncated(self):return False


class ForgeEnv(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self,cfg,family,pool,*,profile='balanced',side=None,scenario=None,seconds=None):
        self.cfg=copy.deepcopy(cfg);self.family=family;self.pool=copy.deepcopy(pool)
        self.seconds=seconds if seconds is not None else cfg['match_seconds']
        if self.seconds<=0:raise ValueError('Match duration must be positive')
        if not pool:raise ValueError('Opponent pool cannot be empty')
        self.profile=profile;self.forced_side=side;self.scenario=scenario
        arena_cfg=load_config(ROOT/'configs/chronos.json')
        arena_cfg['env'].update(learner_hitbox=cfg.get('hitboxes',{}).get(family,'octane'),episode_seconds=self.seconds,no_touch_seconds=self.seconds+1)
        arena_cfg['curriculum']=dict(adaptive=False,weights=PROFILES[profile])
        arena_cfg['objective']=dict(version='goal-potential-v1',**{k:cfg['objective'][k] for k in ('goal','field','distance')})
        self.arena=ForgeArena(arena_cfg)
        self.action_space=spaces.Discrete(90)
        self.actor_size=CORE[family]+3
        self.observation_space=spaces.Box(-np.inf,np.inf,(self.actor_size+90+9,),np.float32)
        self.forecast=BallForecast() if family=='galactus' else None

    @property
    def remaining(self):return max(0,self.seconds-self.decisions/15)

    def _physical_reset(self,scenario):
        # Each reset gets a deterministic seed. Separate streams keep feature
        # slot shuffling from changing the opponent's randomness or spawns.
        seed=int(self.spawn_rng.integers(0,2**31-1))
        self.arena.reset(seed=seed,options=dict(scenario=scenario))
        self.arena.opponent.reset(self.arena.state,self.arena.other,self.opponent_rng)
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32)
        if self.forecast:self.forecast.reset()

    def observation(self):
        base=self.arena.opponent.base
        if hasattr(base,'set_context'):base.set_context(-self.score,self.remaining)
        private=self.arena.opponent.prepare(self.arena.state)
        pred=self.forecast.samples(self.arena.state) if self.forecast else None
        x,self.mirror=build_features(self.arena.state,self.arena.agent,self.previous,self.feature_rng,self.family,pred)
        mask=native_action_mask(self.arena.state.cars[self.arena.agent])
        return np.concatenate((x,context(self.arena.state,self.arena.agent,self.score,self.remaining),mask.astype(np.float32),private))

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        seeds=self.np_random.integers(0,2**31-1,size=3)
        self.spawn_rng=np.random.default_rng(int(seeds[0]));self.feature_rng=np.random.default_rng(int(seeds[1]))
        self.opponent_rng=np.random.default_rng(int(seeds[2]))
        probabilities=np.array([e.get('weight',1) for e in self.pool],dtype=float)
        if not np.isfinite(probabilities).all() or (probabilities<0).any() or probabilities.sum()<=0:raise ValueError('Invalid opponent weights')
        self.arena.entry=self.pool[int(self.np_random.choice(len(self.pool),p=probabilities/probabilities.sum()))]
        self.arena.forced_side=self.forced_side if self.forced_side is not None else int(self.np_random.integers(2))
        self.decisions=0;self.score=0;self.goals_for=0;self.goals_against=0;self.touches=0;self.reward_total=0.
        self.reward_parts={'goal':0.,'match_result':0.,'potential':0.}
        self._physical_reset(self.scenario or self.arena.curriculum.choose(self.spawn_rng))
        return self.observation(),dict(opponent=self.arena.entry['name'],side=self.arena.team)

    def step(self,action):
        action=int(action)
        if not 0<=action<90 or not native_action_mask(self.arena.state.cars[self.arena.agent])[action]:raise ValueError('Invalid/masked direct action')
        planned=TABLE[action].copy()
        if self.mirror:planned[[1,3,4]]*=-1
        commands=np.repeat(self.held[None,:],8,axis=0);commands[7]=planned
        phi=self.arena.potential(self.arena.state)
        goal=0
        for start in (0,2,4,6):
            _,_,scored,_,info=self.arena.step_control_ticks(commands[start:start+2],2,observation=False)
            self.touches+=int(self.arena.state.cars[self.arena.agent].ball_touches)
            if scored:
                goal=info['outcome'];break
        self.previous=planned.copy();self.held=planned.copy();self.decisions+=1
        self.score+=goal;self.goals_for+=int(goal==1);self.goals_against+=int(goal==-1)
        terminal=self.remaining<=1e-6
        if goal and not terminal:self._physical_reset('kickoff')
        # Finite-horizon matches are genuine terminal states: no timeout value
        # bootstrap. A scored goal continues the same match with a kickoff.
        parts=dict(goal=self.cfg['objective']['goal']*goal,
            match_result=self.cfg['objective']['match_result']*float(np.sign(self.score)) if terminal else 0.,
            potential=self.cfg['ppo']['gamma']*(0. if terminal else self.arena.potential(self.arena.state))-phi)
        reward=float(sum(parts.values()));self.reward_total+=reward
        for k,v in parts.items():self.reward_parts[k]+=v
        info=dict(opponent=self.arena.entry['name'],side=self.arena.team,goal=goal)
        if terminal:
            info.update(outcome=int(np.sign(self.score)),goals_for=self.goals_for,goals_against=self.goals_against,
                touches=self.touches,seconds=self.decisions/15,reward_parts=dict(self.reward_parts),
                episode=dict(r=self.reward_total,l=self.decisions))
        # No further queued information is needed at terminal; avoid an extra
        # native query against the goal state. The terminal observation is only
        # used for logging, never bootstrapped.
        obs=self.observation() if not terminal else np.zeros(self.observation_space.shape,np.float32)
        return obs,reward,terminal,False,info

    def close(self):self.arena.close()
