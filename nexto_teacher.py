"""Nexto teacher inference on *RLGym v2* game states.

Uses the original Nexto observation builder and TorchScript weights provided by
Rolv-Arild/Necto (CC BY-NC-SA 4.0). See vendor/nexto/LICENSE.txt.

Replay-state conversion is approximate: this does not reproduce Nexto's full
closed-loop rollout or the RLBot-scripted kickoff sequence.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
NEXTOPATH = ROOT / "vendor" / "nexto"
if str(NEXTOPATH) not in sys.path:
    sys.path.insert(0, str(NEXTOPATH))
from nexto_obs import NextoObsBuilder, rotation_to_quaternion  # noqa: E402
from original_agent import Agent  # noqa: E402

INV = np.array([-1., -1., 1.], dtype=np.float64)
ROT180 = np.diag(INV)


def nexto_actions():
    """Exact Nexto 8-controller-vector discrete lookup table (90 actions)."""
    return np.asarray(Agent.make_lookup_table(), dtype=np.float32)


def action_mapping(student_table: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map Nexto's controls to closest student's lookup action; no action-ID assumptions.

    Penalize mismatches in boolean controls more than steering differences.
    Returns teacher_idx -> student_idx and weighted approximation errors.
    """
    teacher = nexto_actions()
    student = np.asarray(student_table, dtype=np.float32)
    if student.ndim != 2 or student.shape[1] != 8:
        raise ValueError('Expected student action table (N, 8)')
    weights = np.asarray([1., 1., 1., 1., 1., 8., 8., 3.], dtype=np.float32)
    costs = np.sum((teacher[:, None, :] - student[None, :, :])**2 * weights, axis=-1)
    mapping = costs.argmin(axis=1)
    return mapping.astype(np.int64), costs[np.arange(len(teacher)), mapping]


def compress_teacher_probs(logits: np.ndarray, mapping: np.ndarray, target_actions: int = 90,
                           temperature: float = 1.) -> np.ndarray:
    """Preserve probability mass when several Nexto controls map to one RLGym action."""
    if temperature <= 0:
        raise ValueError('temperature must be positive')
    logits = np.asarray(logits, dtype=np.float64)
    if logits.ndim != 2 or logits.shape[1] != len(mapping):
        raise ValueError(f'Logit shape mismatch {logits.shape}')
    v = logits / temperature
    v -= np.max(v, axis=1, keepdims=True)
    probs = np.exp(v)
    probs /= np.sum(probs, axis=1, keepdims=True)
    target = np.zeros((len(logits), target_actions), dtype=np.float32)
    for i, action in enumerate(mapping):
        target[:, action] += probs[:, i].astype(np.float32)
    return target


def _phys_values(physics):
    p = np.asarray(physics.position, dtype=np.float64).reshape(3)
    mat = np.asarray(physics.rotation_mtx, dtype=np.float64).reshape(3, 3)
    v = np.asarray(physics.linear_velocity, dtype=np.float64).reshape(3)
    av = np.asarray(physics.angular_velocity, dtype=np.float64).reshape(3)
    return p, mat, v, av


def _car_block(car, car_index: int) -> list[float]:
    p, rot, vel, omega = _phys_values(car.physics)
    original = np.concatenate([p, rotation_to_quaternion(rot), vel, omega])
    inverted = np.concatenate([p * INV, rotation_to_quaternion(ROT180 @ rot), vel * INV, omega * INV])
    flags = [0., 0., 0., 0., 0.,
             float(bool(getattr(car, 'is_demoed', False))),
             float(bool(getattr(car, 'on_ground', True))),
             float(getattr(car, 'ball_touches', 0) > 0),
             float(bool(getattr(car, 'has_flip', True))),
             # rlgym_compat (Nexto-era) represents car boost on [0, 1].
             # RLGym v2 Car.boost_amount is on [0, 100].
             float(car.boost_amount) / 100.0]
    return [float(car_index), float(bool(car.is_orange)), *original.tolist(), *inverted.tolist(), *flags]


def encode_v2_state(state) -> tuple[np.ndarray, list]:
    """Encode a 1v1 RLGym v2 state into the exact layout expected by Nexto's builder.

    Player order is blue then orange; boost timer 0 means active.
    """
    cars = sorted(state.cars.items(), key=lambda kv: bool(kv[1].is_orange))
    if len(cars) != 2 or cars[0][1].is_orange or not cars[1][1].is_orange:
        raise ValueError('Nexto teacher currently supports 1v1 with one blue and one orange car')
    timers = np.asarray(getattr(state, 'boost_pad_timers'), dtype=np.float32).reshape(-1)
    if timers.shape != (34,):
        raise ValueError(f'Expected 34 boost pad timers, got {timers.shape}')
    active_boosts = (timers <= 1e-6).astype(np.float64)
    ball_p = np.asarray(state.ball.position, dtype=np.float64)
    ball_v = np.asarray(state.ball.linear_velocity, dtype=np.float64)
    ball_w = np.asarray(state.ball.angular_velocity, dtype=np.float64)
    ball = [*ball_p, *ball_v, *ball_w, *(ball_p*INV), *(ball_v*INV), *(ball_w*INV)]
    encoded = [0., 0., 0., *active_boosts.tolist(), *ball]
    for i, (_, car) in enumerate(cars):
        encoded.extend(_car_block(car, i))
    enc = np.asarray(encoded, dtype=np.float64)
    if enc.shape != (131,) or not np.isfinite(enc).all():
        raise ValueError(f'Invalid encoded state: {enc.shape}')
    return enc, [agent for agent, _ in cars]


class NextoTeacher:
    def __init__(self, device: str = 'cpu', batch_size: int = 256):
        import torch
        self.torch = torch
        self.device = torch.device(device)
        self.actor = torch.jit.load(str(NEXTOPATH / 'nexto-model.pt'), map_location=self.device)
        self.actor.eval()
        torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
        self.obs_builder = NextoObsBuilder(n_players=2, tick_skip=8)
        self.batch_size = batch_size

    def observe(self, state, prev_actions: dict) -> list[tuple[object, np.ndarray, np.ndarray, np.ndarray]]:
        encoded, agents = encode_v2_state(state)
        outputs = self.obs_builder.batched_build_obs(encoded[None, :])
        data = []
        for i, agent in enumerate(agents):
            act = np.asarray(prev_actions.get(agent, np.zeros(8)), dtype=np.float64).reshape(8)
            self.obs_builder.add_actions(outputs, act, i)
            q, kv, mask = outputs[i]
            data.append((agent, q[0].astype(np.float32), kv[0].astype(np.float32), mask[0].astype(np.float32)))
        return data

    def logits(self, batch: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> np.ndarray:
        torch = self.torch
        qa = np.stack([x[0] for x in batch], axis=0)
        kva = np.stack([x[1] for x in batch], axis=0)
        ma = np.stack([x[2] for x in batch], axis=0)
        with torch.inference_mode():
            out, _ = self.actor((torch.from_numpy(qa).to(self.device),
                                 torch.from_numpy(kva).to(self.device),
                                 torch.from_numpy(ma).to(self.device)))
        result = out.detach().cpu().numpy()
        if result.ndim != 2 or result.shape[1] != len(nexto_actions()):
            raise ValueError(f'Unexpected Nexto logits shape {result.shape}')
        return result
