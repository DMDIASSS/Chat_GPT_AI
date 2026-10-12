"""Isolated, all-dynamic, goal-tail-aware defender environment (v0.1.8).

This is a research *environment*, not a certified PPO trainer. A short window is
selected from v0.1.6's catalog, not from an arbitrary goal in the NPZ. It uses
inferred attacker controls and free physics for every car; unlike TwoPhaseScenario,
no car is re-teleported on each step.

The environment cannot determine that absence of a goal within the short window
is a real save. It reports ``no_goal_by_deadline`` separately from ``defender_goal``
and never grants a terminal success reward for timeout.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from slater_research.counterfactual_audit import validate_candidate
from slater_research.replay_engine import Clip, FPS, TICKS


class ScenarioError(ValueError):
    """Bad scenario, policy input, or step order."""


@dataclass(frozen=True)
class EpisodeResult:
    status: str
    attacker_scored: bool
    defender_scored: bool
    goal_step: int | None
    completed_steps: int
    goal_offset_s: float | None
    endpoint_ball_error_uu: float | None
    peak_reference_error_uu: float | None
    # Timeouts are not labelled saves.
    defender_touch_observed: bool


def _control(x, *, who: str) -> np.ndarray:
    a = np.asarray(x, dtype=np.float32)
    if a.shape != (8,) or not np.isfinite(a).all():
        raise ScenarioError(f'{who}: expected finite shape (8,) control')
    if np.any(a < -1.0001) or np.any(a > 1.0001):
        raise ScenarioError(f'{who}: controls must be in [-1, 1]')
    return np.clip(a, -1, 1)


def validate_catalog_window(candidate: dict, clip: Clip, *, train_only: bool = True):
    """Reject stale/forged catalog entries before starting RocketSim."""
    required = ('clip_file','split','replay_sha256','window_s','start_step',
                'reference_goal_step','tail_steps','roster_size')
    if not all(k in candidate for k in required):
        raise ScenarioError('Missing catalog metadata')
    if train_only and candidate['split'] != 'train':
        raise ScenarioError('Only train-split catalog entries allowed in training environments')
    start, goal, tail, defenders, orange = validate_candidate(candidate, clip)
    if int(candidate['roster_size']) != len(clip.ids):
        raise ScenarioError('Catalog roster size differs from NPZ')
    expected = (goal - start) * TICKS / FPS
    if not math.isclose(float(candidate['window_s']), expected, abs_tol=TICKS/FPS + 1e-6):
        raise ScenarioError('Catalog window duration inconsistent with stored start and goal')
    # On 1v1, only the single opposing car can learn. Supporting 2v2/3v3 is
    # planned only after replay extraction and physical fidelity have been tested.
    if len(clip.ids) != 2 or len(defenders) != 1:
        raise ScenarioError('v0.1.8 supports verified 1v1 scenarios only')
    if not clip.snapshots[start].cars.get(clip.shooter_id):
        raise ScenarioError('Missing shooter in starting frame')
    return start,goal,tail,defenders,orange


class VerifiedDefenderEnv:
    """Single short replay goal with one trainable defender and fixed deadline.

    Requires a RocketSimEngine-compatible ``engine`` (dependency injected for
    offline tests). Caller owns engine lifecycle and closes it.
    """
    def __init__(self, clip: Clip, candidate: dict, engine, *, train_only: bool = True):
        self.clip=clip
        self.candidate=candidate
        self.engine=engine
        self.start,self.goal,self.tail,self.defenders,self.attacker_orange = (
            validate_catalog_window(candidate,clip,train_only=train_only))
        self.deadline=self.goal+self.tail
        self.index={aid:j for j,aid in enumerate(clip.ids)}
        self.reset()

    def reset(self):
        # Deep copy prevents the engine from modifying the source replay state.
        self.state=self.engine.set_state(copy.deepcopy(self.clip.snapshots[self.start]),{})
        self.i=self.start
        self.done=False
        self.status='in_progress'
        self.goal_step=None
        self.touch_seen={aid:False for aid in self.defenders}
        self.last_touch={aid:False for aid in self.defenders}
        self.errors=[]
        self.endpoint_error=None
        return self.state

    def _inputs(self, overrides: Mapping[int,np.ndarray]):
        if set(overrides)!=set(self.defenders):
            raise ScenarioError(f'Expected exactly defender IDs {self.defenders}, got {tuple(overrides)}')
        commands={}
        for aid in self.clip.ids:
            replay=self.clip.controls[min(self.i,self.goal),self.index[aid]]
            vec=overrides[aid] if aid in overrides else replay
            cmds=_control(vec,who=str(aid))
            commands[aid]=np.tile(cmds,(TICKS,1))
        return commands

    def step(self, defender_actions: Mapping[int,np.ndarray]):
        if self.done:
            raise ScenarioError('Episode is done: call reset() before stepping')
        # Validate all controls before mutating the engine.
        commands=self._inputs(defender_actions)
        self.state=self.engine.step(commands,{})
        self.i+=1
        reward={aid:0. for aid in self.defenders}
        for aid in self.defenders:
            # Car.ball_touches is a step-provided contact signal; reward once
            # per episode to prevent repetitive touches from dominating.
            contact=bool(self.state.cars[aid].ball_touches)
            if contact and not self.touch_seen[aid]:
                reward[aid]+=0.1
                self.touch_seen[aid]=True
            self.last_touch[aid]=contact
        if self.i<=self.goal:
            target=np.asarray(self.clip.snapshots[self.i].ball.position,float)
            error=float(np.linalg.norm(np.asarray(self.state.ball.position,float)-target))
            if not math.isfinite(error):
                raise FloatingPointError('Nonfinite ball trajectory')
            self.errors.append(error)
            if self.i==self.goal:
                self.endpoint_error=error
        if bool(self.state.goal_scored):
            self.done=True
            self.goal_step=self.i
            attacking=bool(self.state.ball.position[1] > 0) != self.attacker_orange
            self.status='attacker_goal' if attacking else 'defender_goal'
            # Rewards intentionally sparse and symmetric. No false positive
            # reward for merely running out of the 0.5/1-second scenario.
            bonus=-5. if attacking else 5.
            for aid in reward: reward[aid]+=bonus
        elif self.i>=self.deadline:
            self.done=True
            self.status='no_goal_by_deadline'
        info={
            'status':self.status,'frame':self.i,'deadline':self.deadline,
            'attacker_goal':self.status=='attacker_goal',
            'defender_goal':self.status=='defender_goal',
            'no_goal_by_deadline':self.status=='no_goal_by_deadline',
            'defender_touch_observed':any(self.touch_seen.values()),
            'endpoint_ball_error_uu':self.endpoint_error,
        }
        return self.state,reward,self.done,info

    def replay_actions(self):
        """Original defender controls for the current decision, including tail."""
        if self.done: raise ScenarioError('Episode is done')
        return {aid:self.clip.controls[min(self.i,self.goal),self.index[aid]].copy()
                for aid in self.defenders}

    def result(self):
        if not self.done: raise ScenarioError('Episode is still running')
        return EpisodeResult(
            status=self.status,
            attacker_scored=self.status=='attacker_goal',
            defender_scored=self.status=='defender_goal',
            goal_step=self.goal_step,
            completed_steps=self.i-self.start,
            goal_offset_s=(self.i-self.goal)*TICKS/FPS if self.goal_step is not None else None,
            endpoint_ball_error_uu=self.endpoint_error,
            peak_reference_error_uu=max(self.errors) if self.errors else None,
            defender_touch_observed=any(self.touch_seen.values()),
        )

    def run_reference(self):
        """Read-only logical rollout with unchanged defender replay controls."""
        self.reset()
        while not self.done:
            self.step(self.replay_actions())
        return self.result()

    def close(self):
        self.engine.close()
