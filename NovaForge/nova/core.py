from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from rlgym_tools.rocket_league.action_parsers.advanced_lookup_table_action import AdvancedLookupTableAction

ROOT = Path(__file__).resolve().parents[1]
TICK_SKIP = 4
OBS_SIZE = 100
# This table is supplied by rlgym-tools (Apache-2.0), not by the downloaded bot.
# Its 276 entries also match Ripple v1.1's table, including ordering/rounding.
ACTIONS = np.asarray(AdvancedLookupTableAction.make_lookup_table(
    [-1, 0, .5, 1], 5, [-1, -.5, 0, .5, 1], 16), dtype=np.float32)
CONTRACT = dict(name='novaforge-v1-1v1', observation=OBS_SIZE, actions=len(ACTIONS),
                action_sha256=hashlib.sha256(ACTIONS.tobytes()).hexdigest(),
                tick_skip=TICK_SKIP, simulator_action_delay_ticks=1)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as f:
            json.dump(value, f, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def model_meta(path):
    return Path(str(path) + '.json')


def check_model(path):
    path = Path(path).resolve()
    meta = json.loads(model_meta(path).read_text(encoding='utf8'))
    if meta.get('contract') != CONTRACT:
        raise ValueError(f'Incompatible model contract: {path}')
    if meta.get('sha256') != sha256(path):
        raise ValueError(f'Model hash mismatch: {path}')
    return meta


def write_model_meta(path, **details):
    atomic_json(model_meta(path), dict(contract=CONTRACT, sha256=sha256(path), **details))


def nearest_action(controls):
    controls = np.asarray(controls, dtype=np.float32)
    if controls.shape != (8,) or not np.isfinite(controls).all():
        raise ValueError('Controls must be eight finite numbers')
    # A jump or boost mismatch matters more than a small analog difference.
    return int(np.square(ACTIONS - controls).dot(np.array([1,1,1,1,1,4,4,2])).argmin())


def _physics(po, invert=False, legacy=False):
    sign = np.array([-1,-1,1], dtype=np.float32) if invert else np.ones(3, dtype=np.float32)
    rotation = po.rotation_mtx() if legacy else po.rotation_mtx
    return (np.asarray(po.position) * sign, np.asarray(po.linear_velocity) * sign,
            np.asarray(po.angular_velocity) * sign, rotation[:,0] * sign, rotation[:,2] * sign)


def _car_features(p, boost, ground, flip, jump, demo):
    pos, vel, ang, forward, up = p
    return np.concatenate((pos/6000, vel/2300, forward, up, ang/6,
                           [boost/100, ground, flip, jump, demo]))


def _assemble(ball, own, other, own_flags, other_flags, pads, previous):
    result = np.concatenate((ball[0]/6000, ball[1]/2300, ball[2]/6,
        _car_features(own, *own_flags), _car_features(other, *other_flags),
        (ball[0]-own[0])/6000, (ball[1]-own[1])/2300,
        (other[0]-own[0])/6000, pads, previous)).astype(np.float32)
    if result.shape != (OBS_SIZE,) or not np.isfinite(result).all():
        raise ValueError(f'Invalid observation: shape {result.shape}')
    return result


def observe(state, agent, previous):
    if len(state.cars) != 2:
        raise ValueError('NovaForge v1 supports exactly 1v1')
    own = state.cars[agent]
    other = next(c for k,c in state.cars.items() if k != agent)
    if own.team_num == other.team_num:
        raise ValueError('Expected one car on each team')
    invert = own.team_num == 1
    def flags(c):
        return (c.boost_amount, c.on_ground, c.has_flip, not c.has_jumped, c.is_demoed)
    pads = (state.boost_pad_timers == 0).astype(np.float32)
    if invert:
        pads = pads[::-1]
    return _assemble(_physics(state.ball, invert), _physics(own.physics, invert),
                     _physics(other.physics, invert), flags(own), flags(other), pads, previous)


def observe_v1(state, own_index, previous):
    """Same feature contract for RLBot v5's V1 compatibility packet."""
    if len(state.players) != 2:
        raise ValueError('NovaForge v1 supports exactly 1v1')
    own, other = state.players[own_index], state.players[1-own_index]
    if own.team_num == other.team_num:
        raise ValueError('Expected one car on each team')
    invert = own.team_num == 1
    def flags(c):
        return (100*c.boost_amount, c.on_ground, c.has_flip, c.has_jump, c.is_demoed)
    pads = np.asarray(state.boost_pads, dtype=np.float32)
    if invert:
        pads = pads[::-1]
    return _assemble(_physics(state.ball, invert, True), _physics(own.car_data, invert, True),
                     _physics(other.car_data, invert, True), flags(own), flags(other), pads, previous)


def as_v1(state, controlled=None):
    from rlgym_tools.rocket_league.v1.convert import convert_game_state
    legacy = convert_game_state(state)
    # RLGym v2 uses 0..100; Nexto/Ripple's V1 observations use 0..1.
    for p in legacy.players:
        p.boost_amount /= 100
    if controlled is not None:
        team = state.cars[controlled].team_num
        legacy.players.sort(key=lambda p: p.team_num != team)
    return legacy


class DecisionClock:
    def __init__(self):
        self.last = None

    def due(self, frame):
        if self.last is None or frame < self.last or frame-self.last >= TICK_SKIP:
            self.last = frame
            return True
        return False
