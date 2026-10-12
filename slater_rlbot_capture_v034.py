"""Small optional telemetry hook used ONLY inside a duplicated RLBot v4 bot.

Captures raw NextoObsBuilder inputs and selected 8-value NN actions, at
infrequent intervals. Does not alter actions or model, no network access.
"""
from __future__ import annotations
import os
from pathlib import Path
import uuid
import numpy as np


def capture_decision(bot, obs, previous_action, selected_action, packet, beta=1.0):
    if not hasattr(bot, '_slater_v034_capture_id'):
        bot._slater_v034_capture_id = uuid.uuid4().hex[:12]
        bot._slater_v034_decision_count = 0
        bot._slater_v034_capture_count = 0
        bot._slater_v034_announced = False
    count = bot._slater_v034_decision_count
    bot._slater_v034_decision_count = count + 1
    every = max(1, min(10000, int(os.environ.get('SLATER_V034_EVERY', '20'))))
    limit = max(1, min(250, int(os.environ.get('SLATER_V034_LIMIT', '50'))))
    if count % every or bot._slater_v034_capture_count >= limit:
        return
    from slater_parity_v034 import canonical_obs
    q, kv, mask = canonical_obs(obs)
    prev = np.asarray(previous_action, dtype=np.float32).reshape(8)
    selected = np.asarray(selected_action, dtype=np.float32).reshape(8)
    packet_car = packet.game_cars[bot.index]
    outdir = Path(__file__).resolve().parent / 'capture_v034'
    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir / f'capture_{bot._slater_v034_capture_id}_{count:06d}.npz'
    if not bot._slater_v034_announced:
        print('SLATER_V034_LIVE_CAPTURE_DIR', outdir, flush=True)
        bot._slater_v034_announced = True
    with fp.open('xb') as out:
        np.savez_compressed(
            out, q=q, kv=kv, mask=mask,
            previous_action=prev, selected_action=selected,
            beta=np.float32(beta), team=np.int32(bot.team), seconds_elapsed=np.float64(packet.game_info.seconds_elapsed),
            is_kickoff_pause=np.bool_(packet.game_info.is_kickoff_pause),
            car_position=np.array([packet_car.physics.location.x, packet_car.physics.location.y,
                                   packet_car.physics.location.z], dtype=np.float32),
            ball_position=np.array([packet.game_ball.physics.location.x,
                                    packet.game_ball.physics.location.y,
                                    packet.game_ball.physics.location.z], dtype=np.float32),
        )
    bot._slater_v034_capture_count += 1
