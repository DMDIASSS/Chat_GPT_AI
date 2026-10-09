"""RLGym v2 reward functions; no fixed bot controls, only learning signals."""
from typing import Any, Dict, List
import numpy as np
from rlgym.api import AgentID, RewardFunction
from rlgym.rocket_league.api import GameState
from rlgym.rocket_league import common_values as cv

from .math_utils import safe_unit


class TowardBall(RewardFunction[AgentID, GameState, float]):
    """Reward driving (or flying) into ball, not merely staying near it."""
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            p = car.physics.position
            delta = state.ball.position - p
            speed = float(np.dot(car.physics.linear_velocity, safe_unit(delta)))
            rewards[agent] = max(0.0, speed) / cv.CAR_MAX_SPEED
        return rewards


class BallTowardGoal(RewardFunction[AgentID, GameState, float]):
    """Score progress from ball velocity toward the actual opponent net."""
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        result = {}
        for agent in agents:
            car = state.cars[agent]
            target_y = -cv.BACK_NET_Y if car.is_orange else cv.BACK_NET_Y
            target = np.array([0., target_y, 300.])
            direction = safe_unit(target - state.ball.position)
            result[agent] = float(np.clip(np.dot(state.ball.linear_velocity, direction) / cv.BALL_MAX_SPEED, -1, 1))
        return result


class AerialTouch(RewardFunction[AgentID, GameState, float]):
    """Promote *actual* contacts at height; does not pay for aimless flying."""
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        return {
            agent: float(state.cars[agent].ball_touches > 0) *
                   float(np.clip((state.ball.position[2] - 250) / 1200, 0, 1))
            for agent in agents
        }


class RecoverySpeed(RewardFunction[AgentID, GameState, float]):
    """Reward landing cleanly: speed matters, but this shouldn't dominate goals."""
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        return {
            a: (max(0., float(np.linalg.norm(c.physics.linear_velocity[:2]))) / cv.CAR_MAX_SPEED)
               if c.on_ground else 0.
            for a, c in ((a, state.cars[a]) for a in agents)
        }
