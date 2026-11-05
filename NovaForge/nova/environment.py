from __future__ import annotations

import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from rlgym.rocket_league.sim import RocketSimEngine

from .core import ACTIONS, OBS_SIZE, TICK_SKIP, observe, sha256
from .scenarios import Curriculum, make_state, practice_success
from .teachers import make_opponent, controls_for_ticks


class ArenaEnv(gym.Env):
    metadata={'render_modes':[]}

    def __init__(self,config,league_manifest=None,opponent=None,snapshot=None,scenario=None,side=None,snapshot_kind='snapshot'):
        super().__init__()
        self.cfg=config
        self.engine=RocketSimEngine(rlbot_delay=True)
        self.action_space=spaces.Discrete(len(ACTIONS))
        self.observation_space=spaces.Box(-np.inf,np.inf,(OBS_SIZE,),np.float32)
        self.league_manifest=Path(league_manifest) if league_manifest else None
        self.forced_opponent=opponent
        self.forced_snapshot=snapshot
        self.snapshot_kind=snapshot_kind
        self.forced_scenario=scenario
        self.forced_side=side
        self.curriculum=Curriculum(config['curriculum']['weights'],config['curriculum']['adaptive'])
        self.cache={}
        self.bank=None
        if config['env'].get('replay_bank'):
            expected=config['env'].get('replay_bank_sha256')
            if expected and sha256(config['env']['replay_bank'])!=expected:
                raise ValueError('Replay reset bank hash mismatch')
            with np.load(config['env']['replay_bank'],allow_pickle=False) as data:
                self.bank=data['states'].copy()
            if self.bank.ndim!=2 or len(self.bank)==0 or not np.isfinite(self.bank).all():
                raise ValueError('Invalid replay reset bank')
        if self.curriculum.weights.get('replay',0)>0 and self.bank is None:
            raise ValueError('Replay resets have weight but no replay_bank is configured')

    def _choose_opponent(self,_snapshot_retries=0):
        path=self.forced_snapshot
        if self.forced_opponent:
            name=self.forced_opponent
        else:
            weights=self.cfg['league']['weights']
            names=list(weights)
            probabilities=np.asarray(list(weights.values()),dtype=np.float64)
            name=str(self.np_random.choice(names,p=probabilities/probabilities.sum()))
        label=name
        if name in ('latest','history'):
            entries=[]
            if self.league_manifest and self.league_manifest.exists():
                entries=json.loads(self.league_manifest.read_text())['snapshots']
            if entries:
                chosen=entries[-1] if name=='latest' else entries[int(self.np_random.integers(len(entries)))]
                path=self.league_manifest.parent/chosen['path']
                label=f'{name}:{chosen["step"]}'
                name=self.snapshot_kind
            else:
                name='scripted'
                label='scripted:empty-snapshot-pool'
        key=(name,str(path))
        if key not in self.cache:
            try:self.cache[key]=make_opponent(name,path)
            except FileNotFoundError:
                # A worker may read the previous atomic manifest immediately
                # before the learner switches it and prunes inactive actors.
                if label.split(':')[0] in ('latest','history') and self.league_manifest and _snapshot_retries<3:
                    return self._choose_opponent(_snapshot_retries+1)
                raise
            # Keep at most four snapshot actors in each worker's RAM.
            snapshots=[k for k in self.cache if k[0] in ('snapshot','chronos_snapshot')]
            for old in snapshots[:-4]: self.cache.pop(old)
        self.opponent=self.cache[key]
        self.opponent_label=label

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        options=options or {}
        self.scenario=options.get('scenario',self.forced_scenario) or self.curriculum.choose(self.np_random)
        side=self.forced_side if self.forced_side is not None else int(self.np_random.integers(2))
        desired=make_state(self.engine,self.np_random,self.scenario,side,
                           self.curriculum.difficulty(self.scenario),self.bank)
        self.state=self.engine.set_state(desired,{})
        self.agent=next(k for k,c in self.state.cars.items() if c.team_num==side)
        self.other=next(k for k in self.state.cars if k!=self.agent)
        self.team=side
        self.previous=np.zeros(8,dtype=np.float32)
        self.steps=0
        self.since_touch=0
        self.own_touches=0
        self.high_touch=False
        self.wall_touch=False
        self.dribble_seconds=0.
        self.reward_total=0.
        self.reward_parts={}
        self._choose_opponent()
        self.opponent.reset(self.state,self.other,self.np_random)
        return observe(self.state,self.agent,self.previous),{'scenario':self.scenario,'side':side}

    def _reward(self,old,new,outcome,terminated):
        car=new.cars[self.agent]
        old_car=old.cars[self.agent]
        dt=TICK_SKIP/120
        direction=1 if self.team==0 else -1
        phi_old=direction*old.ball.position[1]/5200
        phi_new=0 if terminated else direction*new.ball.position[1]/5200
        delta=new.ball.position-car.physics.position
        distance=np.linalg.norm(delta)
        closing=np.dot(car.physics.linear_velocity,delta/max(distance,1))/2300
        touched=car.ball_touches>0
        altitude=float(np.clip((new.ball.position[2]-150)/1000,0,1)) if touched else 0.
        goal_delta=np.array([0,direction*5120,321])-new.ball.position
        toward_goal=np.dot(new.ball.linear_velocity,goal_delta/max(np.linalg.norm(goal_delta),1))/2300
        parts=dict(goal=10*outcome,potential=.5*(self.cfg['ppo']['gamma']*phi_new-phi_old),
                   approach=.12*dt*float(np.clip(closing,-1,1)),touch=.2*float(touched),
                   high_touch=.5*altitude,ball_progress=.08*dt*float(np.clip(toward_goal,-1,1)),
                   boost_cost=-.01*max(0,old_car.boost_amount-car.boost_amount)/100)
        if self.cfg['rewards']=='sparse': parts={'goal':10*outcome}
        for k,v in parts.items(): self.reward_parts[k]=self.reward_parts.get(k,0.)+float(v)
        return float(sum(parts.values()))

    def step(self,action):
        return self.step_controls(ACTIONS[int(action)])

    def _truncated(self):
        return (self.steps*TICK_SKIP>=self.cfg['env']['episode_seconds']*120 or
                self.since_touch>=self.cfg['env']['no_touch_seconds']*120)

    def step_controls(self,controls):
        controls=np.asarray(controls,dtype=np.float32)
        if controls.shape==(8,): controls=np.repeat(controls[None,:],TICK_SKIP,axis=0)
        if controls.shape!=(TICK_SKIP,8) or not np.isfinite(controls).all() or np.max(np.abs(controls))>1.001:
            raise ValueError('Invalid learner controls')
        old=self.state
        opponent_actions=controls_for_ticks(self.opponent,old)
        self.state=self.engine.step({self.agent:controls,self.other:opponent_actions},{})
        self.previous=controls[-1].copy()
        self.steps+=1
        touches=sum(c.ball_touches for c in self.state.cars.values())
        self.since_touch=0 if touches else self.since_touch+TICK_SKIP
        own=self.state.cars[self.agent]
        if own.ball_touches:
            self.own_touches+=int(own.ball_touches)
            self.high_touch |= self.state.ball.position[2]>250
            self.wall_touch |= abs(self.state.ball.position[0])>3300 and self.state.ball.position[2]>180
        rel=self.state.ball.position-own.physics.position
        if own.on_ground and 70<rel[2]<200 and np.linalg.norm(rel[:2])<130:
            self.dribble_seconds+=TICK_SKIP/120
        terminated=bool(self.state.goal_scored)
        # Goal takes precedence over a simultaneous horizon/timeout.
        truncated=not terminated and self._truncated()
        outcome=(1 if self.state.scoring_team==self.team else -1) if terminated else 0
        reward=self._reward(old,self.state,outcome,terminated)
        self.reward_total+=reward
        info={'scenario':self.scenario,'opponent':self.opponent_label,'side':self.team}
        if terminated or truncated:
            success=practice_success(self.scenario,self.state,self.agent,self.own_touches,
                            self.high_touch,self.wall_touch,self.dribble_seconds,outcome)
            self.curriculum.record(self.scenario,success)
            info.update(outcome=outcome,timeout=bool(truncated),practice_success=bool(success),
                touches=self.own_touches,high_touch=bool(self.high_touch),wall_touch=bool(self.wall_touch),
                dribble_seconds=self.dribble_seconds,seconds=self.steps*TICK_SKIP/120,
                reward_parts=dict(self.reward_parts),
                episode={'r':self.reward_total,'l':self.steps})
        return observe(self.state,self.agent,self.previous),reward,terminated,truncated,info

    def close(self):
        self.engine.close()
