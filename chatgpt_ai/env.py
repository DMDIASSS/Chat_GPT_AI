"""Single source of truth for training / replay / RLBot observation semantics."""
import numpy as np
from rlgym.rocket_league import common_values as cv

from .config import TICK_SKIP, PRESETS


def make_obs():
    from rlgym.rocket_league.obs_builders import DefaultObs
    return DefaultObs(
        zero_padding=None,  # 1v1 only; 92 features with exactly two cars.
        pos_coef=np.asarray([1 / cv.SIDE_WALL_X, 1 / cv.BACK_NET_Y, 1 / cv.CEILING_Z]),
        ang_coef=1 / np.pi,
        lin_vel_coef=1 / cv.CAR_MAX_SPEED,
        ang_vel_coef=1 / cv.CAR_MAX_ANG_VEL,
        boost_coef=1 / 100.0,
    )


def make_action_parser():
    from rlgym.rocket_league.action_parsers import LookupTableAction, RepeatAction
    return RepeatAction(LookupTableAction(), repeats=TICK_SKIP)


def make_rewards(preset: str):
    from rlgym.rocket_league.reward_functions import CombinedReward, GoalReward, TouchReward
    from .rewards import TowardBall, BallTowardGoal, AerialTouch, RecoverySpeed
    if preset == "grounded":
        from .grounded_rewards import ApproachProgress, BallProgressToGoal, UsefulTouchImpulse, WastedLowBallAirTime
        return CombinedReward(
            (GoalReward(), 12.0),
            (TouchReward(), 1.0),
            (ApproachProgress(), 3.0),
            (BallProgressToGoal(), 3.0),
            (UsefulTouchImpulse(), 1.0),
            (WastedLowBallAirTime(), 0.01),
        )
    # All presets use goals as the most consequential event. Avoid rewards for
    # gratuitous jumps or only sitting close to the ball.
    weights = {
        "smoke": (10., .2, .03, .2, .0, .0),
        "fundamentals": (10., .25, .03, .20, .0, .002),
        "balanced": (10., .3, .025, .25, .5, .002),
        "mechanics": (10., .3, .015, .3, 1.5, .003),
        "competitive": (10., .3, .02, .3, .7, .002),
    }
    goal, touch, toward, shot, aerial, recovery = weights[preset]
    return CombinedReward(
        (GoalReward(), goal), (TouchReward(), touch),
        (TowardBall(), toward), (BallTowardGoal(), shot),
        (AerialTouch(), aerial), (RecoverySpeed(), recovery),
    )


def build_env(preset: str = "balanced"):
    if preset not in PRESETS:
        raise ValueError(f"Invalid preset {preset}")
    from rlgym.api import RLGym
    from rlgym.rocket_league.done_conditions import (
        AnyCondition, GoalCondition, NoTouchTimeoutCondition, TimeoutCondition,
    )
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import MutatorSequence, FixedTeamSizeMutator
    from rlgym_ppo.util import RLGymV2GymWrapper
    from .curriculum import ChatGPTCurriculum

    env = RLGym(
        state_mutator=MutatorSequence(
            FixedTeamSizeMutator(blue_size=1, orange_size=1), ChatGPTCurriculum(preset)),
        obs_builder=make_obs(),
        action_parser=make_action_parser(),
        reward_fn=make_rewards(preset),
        termination_cond=GoalCondition(),
        truncation_cond=AnyCondition(
            NoTouchTimeoutCondition(timeout_seconds=25),
            TimeoutCondition(timeout_seconds=180),
        ),
        transition_engine=RocketSimEngine(),
    )
    return RLGymV2GymWrapper(env)
