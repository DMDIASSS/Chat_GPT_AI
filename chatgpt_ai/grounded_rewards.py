"""Grounded-play reward experiment for RLGym v2.

Inspired by potential-based shaping and event-based contact, NOT copied from Necto.
No continuous reward for spinning, idle boost consumption, or staying airborne.
All components return one reward per agent per step.
"""
from __future__ import annotations
from typing import Any, Dict, List

import numpy as np
from rlgym.api import AgentID, RewardFunction
from rlgym.rocket_league.api import GameState
from rlgym.rocket_league import common_values as cv


def _approach_potential(position, ball_position) -> float:
    return float(np.exp(-np.linalg.norm(np.asarray(ball_position)-np.asarray(position)) / 1600.0))


def _goal_potential(ball_position, is_orange) -> float:
    # Blue attacks +Y; orange attacks -Y.
    signed_y = -float(ball_position[1]) if is_orange else float(ball_position[1])
    return float(np.clip(signed_y / cv.BACK_NET_Y, -1.0, 1.0))


class ApproachProgress(RewardFunction[AgentID, GameState, float]):
    """Pay for DECREASING distance to ball, not ongoing speed/spinning.

    This remains limited shaping, not a replacement for scoring/contact.
    """
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.previous = {a: _approach_potential(initial_state.cars[a].physics.position, initial_state.ball.position) for a in agents}

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {}
        for a in agents:
            car = state.cars[a]
            curr = _approach_potential(car.physics.position, state.ball.position)
            # Focus this preset on low ball/ground mechanics. No abrupt penalty when jumping.
            eligible = car.on_ground and state.ball.position[2] < 400
            rewards[a] = (curr - self.previous[a]) if eligible else 0.0
            self.previous[a] = curr
        return rewards


class BallProgressToGoal(RewardFunction[AgentID, GameState, float]):
    """Ball position DELTA, rather than getting paid every frame for ball velocity."""
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.previous = {a: _goal_potential(initial_state.ball.position, initial_state.cars[a].is_orange) for a in agents}

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {}
        for a in agents:
            curr = _goal_potential(state.ball.position, state.cars[a].is_orange)
            rewards[a] = curr - self.previous[a]
            self.previous[a] = curr
        return rewards


class UsefulTouchImpulse(RewardFunction[AgentID, GameState, float]):
    """Only score positive ball velocity CHANGE toward opponent's goal on actual touch."""
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.previous_ball_velocity = np.asarray(initial_state.ball.linear_velocity, dtype=np.float64).copy()

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        v = np.asarray(state.ball.linear_velocity, dtype=np.float64)
        delta_v = v - self.previous_ball_velocity
        rewards = {}
        for a in agents:
            car = state.cars[a]
            attack = -1.0 if car.is_orange else 1.0
            impulse = float(np.clip(delta_v[1] * attack / cv.BALL_MAX_SPEED, 0.0, 1.0))
            rewards[a] = impulse if car.ball_touches > 0 else 0.0
        self.previous_ball_velocity = v.copy()
        return rewards


class WastedLowBallAirTime(RewardFunction[AgentID, GameState, float]):
    """Small penalty for airborne time far from low ball; doesn't ban useful flips."""
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {}
        ball_pos = np.asarray(state.ball.position)
        for a in agents:
            car = state.cars[a]
            distance = float(np.linalg.norm(ball_pos - car.physics.position))
            rewards[a] = -1.0 if not car.on_ground and ball_pos[2] < 300 and distance > 900 else 0.0
        return rewards
