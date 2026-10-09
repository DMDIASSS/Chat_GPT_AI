"""Scenario reset distribution: exposes agent to non-kickoff states early.

Mechanics presets provide useful aerial/wall/ground states, not guaranteed skills.
"""
import random
from typing import Any, Dict
import numpy as np
from rlgym.api import StateMutator
from rlgym.rocket_league.api import GameState
from rlgym.rocket_league.state_mutators import KickoffMutator

from .curriculum_config import DISTRIBUTIONS, choose_scenario
from .math_utils import facing_matrix


class ChatGPTCurriculum(StateMutator[GameState]):
    def __init__(self, preset: str):
        if preset not in DISTRIBUTIONS:
            raise ValueError(f"Unknown preset: {preset}")
        self.preset = preset
        self.kickoff = KickoffMutator()

    def apply(self, state: GameState, shared_info: Dict[str, Any]) -> None:
        # Kickoff initialises every mutable field and boost timers first.
        self.kickoff.apply(state, shared_info)
        scenario = choose_scenario(self.preset)
        if scenario == "kickoff":
            return

        # Ball physics: always in bounds and clear of floor/car spawn.
        bx = random.uniform(-2100, 2100)
        by = random.uniform(-3100, 3100)
        bz = {"ground": 115., "defense": 125., "aerial": random.uniform(450, 1300),
              "wall": random.uniform(220, 900)}[scenario]
        if scenario == "wall":
            bx = random.choice([-1., 1.]) * random.uniform(3300, 3750)
        bpos = np.array([bx, by, bz], dtype=float)
        bvel = np.array([random.uniform(-750, 750), random.uniform(-1000, 1000),
                         random.uniform(-150, 350)], dtype=float)
        if scenario in ("aerial", "wall"):
            bvel[2] = random.uniform(-350, 450)
        state.ball.position = bpos
        state.ball.linear_velocity = bvel
        state.ball.angular_velocity = np.zeros(3)

        # 1v1: don't overlap cars or the ball. Both teams see symmetric episodes.
        for i, (_, car) in enumerate(state.cars.items()):
            sign = 1 if car.is_orange else -1
            if scenario == "defense":
                x = bx + random.uniform(-550, 550)
                y = sign * random.uniform(3350, 4350)
                z = 17.
            elif scenario == "aerial":
                x = bx + random.uniform(-800, 800)
                y = by + sign * random.uniform(600, 1300)
                z = random.uniform(110, 250)
            elif scenario == "wall":
                x = float(np.clip(bx - np.sign(bx) * random.uniform(400, 750), -3800, 3800))
                y = by + sign * random.uniform(400, 750)
                z = 17.
            else:
                x = bx + random.uniform(-1100, 1100)
                y = by + sign * random.uniform(600, 1500)
                z = 17.
            x = float(np.clip(x, -3800, 3800))
            y = float(np.clip(y, -4500, 4500))
            p = np.array([x, y, z], dtype=float)
            car.physics.position = p
            car.physics.rotation_mtx = facing_matrix(bpos - p)
            car.physics.linear_velocity = np.array([random.uniform(-150, 150),
                                                     random.uniform(-300, 300), 0.])
            car.physics.angular_velocity = np.zeros(3)
            car.boost_amount = random.uniform(35, 100)
