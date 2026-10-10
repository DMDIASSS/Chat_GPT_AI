"""Frozen Nexto/Cycle9/Wavedash CPU inference for GigaLearn's C++ RocketSim state.

Source of Nexto observation equations: Rolv-Arild/Necto, CC BY-NC-SA 4.0.
Strict action-table and checkpoint architecture validation. No trainable parameters.
Each inference batch consists of one 1v1 game per arena, 89 floats per arena.
Note: This does NOT include RLBot's scripted kickoff override.
"""
from __future__ import annotations
import hashlib
import os
import sys
from pathlib import Path
# The Windows C++ embedded interpreter is configured against system Python 3.11;
# use the *same* project's Python 3.11 .venv wheel packages, if present.
_pkgdir = os.environ.get('GL_FROZEN_SITE_PACKAGES', '')
_dll_dirs = []
if _pkgdir:
    if not Path(_pkgdir).is_dir():
        raise FileNotFoundError('GL_FROZEN_SITE_PACKAGES does not exist: ' + _pkgdir)
    sys.path.insert(0, _pkgdir)
    _torch_dll_dir = Path(_pkgdir) / 'torch' / 'lib'
    if os.name == 'nt' and _torch_dll_dir.is_dir():
        _dll_dirs.append(os.add_dll_directory(str(_torch_dll_dir)))
import numpy as np
import torch
from nexto_obs import NextoObsBuilder, rotation_to_quaternion

FRAME = 89
CAR = 23
INV = np.array([-1., -1., 1.], dtype=np.float64)
ROT180 = np.diag(INV)


def _car_block(a: np.ndarray, team: int) -> list[float]:
    p = a[0:3].astype(np.float64)
    f, r, u = (a[3:6], a[6:9], a[9:12])
    mat = np.column_stack((f, r, u)).astype(np.float64)
    # Basis must be a proper rotation. Abort instead of feeding corrupt Nexto obs.
    if not np.allclose(mat.T @ mat, np.eye(3), atol=.06) or not np.isclose(np.linalg.det(mat), 1., atol=.06):
        raise ValueError('Car orientation has invalid basis; check RocketSim rotation convention')
    v, w = a[12:15].astype(np.float64), a[15:18].astype(np.float64)
    orig = [*p, *rotation_to_quaternion(mat), *v, *w]
    inverted = [*(p * INV), *rotation_to_quaternion(ROT180 @ mat), *(v * INV), *(w * INV)]
    boost, grounded, flip, demo, touch = a[18:23]
    flags = [0., 0., 0., 0., 0., float(demo > .5), float(grounded > .5),
             float(touch > .5), float(flip > .5), float(boost) / 100.]
    return [float(team), float(team), *orig, *inverted, *flags]


def encode_frame(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    if frame.shape != (FRAME,) or not np.all(np.isfinite(frame)):
        raise ValueError('Expected one finite 89-float frame (boost34, ball9, blue23, orange23)')
    ball = frame[34:43].astype(np.float64)
    bp, bv, bw = ball[:3], ball[3:6], ball[6:9]
    state = [0., 0., 0., *frame[:34].astype(np.float64),
             *bp, *bv, *bw, *(bp * INV), *(bv * INV), *(bw * INV),
             *_car_block(frame[43:66], 0), *_car_block(frame[66:89], 1)]
    out = np.array(state, dtype=np.float64)
    if out.shape != (131,) or not np.all(np.isfinite(out)):
        raise AssertionError(f'Nexto encoded state length was {out.shape}, expected 131')
    return out


class FrozenRotation:
    def __init__(self, paths: dict, cpp_controls: np.ndarray, teacher_device='cpu'):
        expected_names = {'nexto', 'cycle9', 'wavedash'}
        if set(paths) != expected_names:
            raise ValueError('Must provide exactly nexto, cycle9, wavedash paths')
        self.torch = torch
        self.device = torch.device(teacher_device)
        if self.device.type != 'cpu':
            raise ValueError('Use CPU for the frozen teacher on the 4GB-VRAM GTX 1650')
        self.obs = NextoObsBuilder(n_players=2, tick_skip=8)
        cpp_controls = np.asarray(cpp_controls, dtype=np.float32)
        if cpp_controls.shape != (90, 8):
            raise ValueError(f'GigaLearn action lookup must be (90,8), got {cpp_controls.shape}')
        from_original = self._original_actions()
        error = np.abs(cpp_controls - from_original).max()
        if error > 1e-5:
            raise ValueError(f'Nexto and GigaLearn action tables DO NOT MATCH (error {error})')
        self.actors = {}
        self.hashes = {}
        baseline = Path(paths['nexto'])
        if not baseline.is_file():
            raise FileNotFoundError(f'Original Nexto TorchScript model missing: {baseline}')
        # Load each separately; no actor weights ever modified in a training step.
        for name in ('nexto', 'cycle9', 'wavedash'):
            path = Path(paths[name])
            if not path.is_file():
                raise FileNotFoundError(f'Missing {name} actor checkpoint: {path}')
            actor = torch.jit.load(str(baseline), map_location=self.device)
            if name != 'nexto':
                # Only permit state_dict-style Nexto checkpoints, not arbitrary pickled models.
                data = torch.load(str(path), map_location='cpu', weights_only=True)
                if not isinstance(data, dict) or not isinstance(data.get('actor'), dict):
                    raise ValueError(f'{name} is not a native Nexto actor-state checkpoint')
                actor.load_state_dict(data['actor'], strict=True)
            actor.eval()
            self.actors[name] = actor
            self.hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.name = 'nexto'
        self.prev = {}
        self.last_actions = np.zeros((0, 8), dtype=np.float32)
        print('[FrozenNexto] loaded validated actors; action table exact match, teacher CPU', flush=True)
        for n, h in self.hashes.items():
            print('[FrozenNexto] actor', n, h[:16], flush=True)

    @staticmethod
    def _original_actions():
        result = []
        for throttle in (-1, 0, 1):
            for steer in (-1, 0, 1):
                for boost in (0, 1):
                    for handbrake in (0, 1):
                        if boost and throttle != 1:
                            continue
                        result.append([throttle or boost, steer, 0, steer, 0, 0, boost, handbrake])
        for pitch in (-1, 0, 1):
            for yaw in (-1, 0, 1):
                for roll in (-1, 0, 1):
                    for jump in (0, 1):
                        for boost in (0, 1):
                            if jump and yaw != 0:
                                continue
                            if pitch == roll == jump == 0:
                                continue
                            handbrake = int(bool(jump and (pitch or yaw or roll)))
                            result.append([boost, yaw, pitch, yaw, roll, jump, boost, handbrake])
        return np.asarray(result, dtype=np.float32)

    def select(self, name: str):
        if name not in self.actors:
            raise ValueError('Unknown teacher ' + name)
        if name != self.name:
            self.prev.clear()
            self.name = name
            print('[FrozenNexto] teacher rotation ->', name, flush=True)

    def infer(self, frames, reset_flags, opponent_is_orange: bool):
        data = np.asarray(frames, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != FRAME or len(data) == 0:
            raise ValueError('Expected Bx89 RocketSim game state batch')
        resets = np.asarray(reset_flags, dtype=np.uint8).reshape(-1)
        if len(resets) != len(data):
            raise ValueError('Reset vector shape mismatch')
        qs, kvs, masks = [], [], []
        car_idx = int(bool(opponent_is_orange))
        for i, frame in enumerate(data):
            if resets[i]:
                self.prev.pop(i, None)
            state = encode_frame(frame)
            q, kv, mask = self.obs.batched_build_obs(state[np.newaxis, :])[car_idx]
            q, kv, mask = q[0].astype(np.float32), kv[0].astype(np.float32), mask[0].astype(np.float32)
            q[0, 24:32] = self.prev.get(i, np.zeros(8, dtype=np.float32))
            qs.append(q)
            kvs.append(kv)
            masks.append(mask)
        with torch.inference_mode():
            prediction, _ = self.actors[self.name]((torch.from_numpy(np.stack(qs)).to(self.device),
                                                    torch.from_numpy(np.stack(kvs)).to(self.device),
                                                    torch.from_numpy(np.stack(masks)).to(self.device)))
            if prediction.shape != (len(data), 90):
                raise ValueError(f'Unexpected policy output shape: {tuple(prediction.shape)}')
            choices = prediction.argmax(-1).cpu().numpy().astype(np.int64)
        lookup = self._original_actions()
        for i, idx in enumerate(choices):
            if idx < 0 or idx >= 90:
                raise ValueError('Action out of range')
            self.prev[i] = lookup[idx].copy()
        return choices.tolist()
