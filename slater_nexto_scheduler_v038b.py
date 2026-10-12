"""Slater v0.3.8b: source-matched RLBot v4 Nexto per-physics-tick state machine.

This is a standalone, pure Python emulation of Nexto's get_output / maybe_do_kickoff
control scheduling. Inference is injected via `infer(prev_action, beta)`; the
caller supplies state and an explicit kickoff-pause boolean per 120Hz packet.

CAUTION: RocketSim has no authoritative packet.game_info.is_kickoff_pause;
the separately packaged adapter uses a labeled proxy. This is NOT live parity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable
import numpy as np

VERSION = 'v0.3.8b'
# Copied from exact stage table previously verified against RLBotPack Nexto.
STAGES = (
    (44, (1, 0, 0, 0, 0, 0, 1, 0)),
    (16, (1, -1, 0, 0, 0, 0, 1, 0)),
    (8, (1, 0, 0, 0, 0, 1, 1, 0)),
    (4, (1, 0, 0, 0, 0, 0, 1, 0)),
    (4, (1, 0, -.7, .8, 0, 1, 1, 0)),
    (52, (1, 0, 1, 0, 0, 0, 1, 0)),
    (40, (1, 0, .5, 0, 1, 0, 0, 0)),
)
KICKOFF = np.concatenate([np.repeat(np.asarray(x, dtype=np.float32)[None], n, axis=0) for n,x in STAGES])
KICKOFF_SHA = '6f3b9fadf306e5f1275a149ecb672028258086586cbdd1190fe533c25248fc88'
assert KICKOFF.shape == (168, 8)
assert hashlib.sha256(KICKOFF.astype('<f4').tobytes()).hexdigest() == KICKOFF_SHA


@dataclass
class Frame:
    controls: np.ndarray
    action: np.ndarray
    kickoff_index: int
    script_applied: bool
    script_interrupted: bool
    neural_updated: bool
    beta: float | None
    sampled_action: int | None


class NextoV4Clock:
    """Exact control-flow order from archived Nexto v4 bot.py, when ticks_elapsed=1.

    The reference implementation mutates `self.action` when a script overrides
    the neural action, and the PREVIOUS action in the next observation must
    reflect that mutation. Preserving this matters during sampling.
    """
    def __init__(self, *, hardcoded=True, stochastic=True, beta=1.0, tick_skip=8):
        if tick_skip != 8:
            raise ValueError('This reference snapshot uses tick_skip 8')
        self.hardcoded = bool(hardcoded)
        self.stochastic = bool(stochastic)
        self.beta = float(beta)
        self.reset()

    def reset(self):
        self.ticks = 8
        self.update_action = True
        self.kickoff_index = -1
        self.action = np.zeros(8, dtype=np.float32)
        self.controls = np.zeros(8, dtype=np.float32)
        self.nn_inferences = 0
        self.script_physics_ticks = 0
        self.interrupted_physics_ticks = 0
        self.stochastic_nn_inferences = 0
        self.frame_count = 0

    @staticmethod
    def kickoff_taker(positions: np.ndarray, teams: np.ndarray, index: int,
                      ball_xy: np.ndarray) -> bool:
        """Faithful port of the REFERENCE CODE, including its left-goes branch.

        Note: source code has `if not is_left: is_kickoff_taker=False`, which
        may not match the intent expressed in its `# Left goes` comment.
        """
        positions = np.asarray(positions, dtype=np.float64)
        teams = np.asarray(teams)
        ball_xy = np.asarray(ball_xy, dtype=np.float64)
        if positions.ndim != 2 or positions.shape[1] != 2 or teams.shape != (len(positions),):
            raise ValueError('Invalid kickoff position/team table')
        if not 0 <= index < len(positions):
            raise ValueError('Invalid current player index')
        dist = np.linalg.norm(positions - ball_xy, axis=1)
        if abs(float(dist.min() - dist[index])) > 10:
            return False
        taking = True
        for j in np.argsort(dist):
            if abs(float(dist[j] - dist[index])) <= 10 and teams[j] == teams[index] and j != index:
                is_left = (positions[j, 0] < positions[index, 0]) if teams[index] == 0 else (positions[j, 0] > positions[index, 0])
                if not is_left:
                    taking = False
        return taking

    def frame(self, *, is_kickoff_pause: bool, ball_xy, positions, teams, index: int,
              infer: Callable[[np.ndarray, float], tuple[int, np.ndarray]],
              ticks_elapsed: int = 1, match_ended=False) -> Frame:
        if not isinstance(ticks_elapsed, int) or ticks_elapsed < 0:
            raise ValueError('ticks_elapsed must be a nonnegative integer')
        self.ticks += ticks_elapsed
        neural_updated = False
        selected = None
        beta = None
        if self.update_action:
            self.update_action = False
            beta = 0.0 if match_ended else self.beta
            if self.stochastic and is_kickoff_pause:
                beta = 0.5
            prev = self.action.copy()
            selected, action = infer(prev, beta)
            a = np.asarray(action, dtype=np.float32).reshape(8)
            if not np.isfinite(a).all():
                raise FloatingPointError('Nonfinite sampled Nexto control')
            self.action = a.copy()
            self.nn_inferences += 1
            neural_updated = True
            if beta == 0.5:
                self.stochastic_nn_inferences += 1

        if self.ticks >= 7:
            self.controls = self.action.copy()
        if self.ticks >= 8:
            self.ticks = 0
            self.update_action = True

        scripted = False
        interrupted = False
        if self.hardcoded:
            if is_kickoff_pause:
                if self.kickoff_index >= 0:
                    self.kickoff_index += round(ticks_elapsed)
                elif self.kickoff_index == -1:
                    if self.kickoff_taker(positions, teams, index, ball_xy):
                        self.kickoff_index = 0
                    else:
                        self.kickoff_index = -2
                if 0 <= self.kickoff_index < len(KICKOFF):
                    if float(np.asarray(ball_xy)[1]) == 0.0:
                        self.action = KICKOFF[self.kickoff_index].copy()
                        self.controls = self.action.copy()
                        scripted = True
                        self.script_physics_ticks += 1
                    else:
                        interrupted = True
                        self.interrupted_physics_ticks += 1
            else:
                self.kickoff_index = -1
        self.frame_count += 1
        return Frame(self.controls.copy(), self.action.copy(), self.kickoff_index,
                     scripted, interrupted, neural_updated, beta, selected)
