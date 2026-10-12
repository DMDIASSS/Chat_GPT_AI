"""Passive per-packet telemetry for isolated RLBot v4 Nexto copy.

Captures controls and packet kickoff flags without modifying bot decisions.
The installer ensures this is copied only into a new diagnostic folder.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import uuid

import numpy as np

SCHEMA='slater_nexto_live_v038c_v1'


def control_vec(controller):
    return [float(controller.throttle),float(controller.steer),float(controller.pitch),
            float(controller.yaw),float(controller.roll),float(bool(controller.jump)),
            float(bool(controller.boost)),float(bool(controller.handbrake))]


def flush(bot):
    buf=getattr(bot,'_v038c_buffer',[])
    if not buf:return
    p=bot._v038c_file
    with p.open('a',encoding='utf8',newline='\n') as f:
        for r in buf:
            f.write(json.dumps(r,allow_nan=False,separators=(',',':'))+'\n')
    bot._v038c_buffer=[]


def record(bot, packet, ticks_elapsed, was_neural, neural_action, beta):
    if not hasattr(bot,'_v038c_file'):
        folder=Path(__file__).resolve().parent/'capture_v038c'
        folder.mkdir(parents=True,exist_ok=True)
        p=folder/('nexto_live_'+uuid.uuid4().hex[:16]+'.jsonl')
        with p.open('x',encoding='utf8') as f:
            f.write(json.dumps({'schema':SCHEMA,'kind':'meta','flags':{
                'hardcoded':bool(bot.hardcoded_kickoffs),'stochastic':bool(bot.stochastic_kickoffs),
                'beta':float(bot.beta),'tick_skip':int(bot.tick_skip)},
                'source':'archived_stock_nexto_from_user_rlbotpack','capture_only':True})+'\n')
        bot._v038c_file=p
        bot._v038c_count=0
        bot._v038c_buffer=[]
        atexit.register(flush,bot)
        print('V038C_LIVE_TRACE',p,flush=True)
    n=bot._v038c_count
    cap=int(os.environ.get('SLATER_V038C_MAX_FRAMES','3600'))
    if cap<1 or cap>50000:cap=3600
    if n>=cap:return
    car_data=[{'pos':[float(c.physics.location.x),float(c.physics.location.y)],
               'team':int(c.team)} for c in packet.game_cars[:packet.num_cars]]
    r={
        'kind':'frame','packet_index':n,
        'seconds_elapsed':float(packet.game_info.seconds_elapsed),
        'ticks_elapsed':int(ticks_elapsed),
        'is_kickoff_pause':bool(packet.game_info.is_kickoff_pause),
        'is_round_active':bool(packet.game_info.is_round_active),
        'is_match_ended':bool(packet.game_info.is_match_ended),
        'ball_xy':[float(packet.game_ball.physics.location.x),float(packet.game_ball.physics.location.y)],
        'cars':car_data,'player_index':int(bot.index),
        'neural_updated':bool(was_neural),
        'selected_nn_action':None if neural_action is None else np.asarray(neural_action,dtype=np.float32).reshape(8).tolist(),
        'selected_beta':beta,
        'post_action':np.asarray(bot.action,dtype=np.float32).reshape(8).tolist(),
        'controls':control_vec(bot.controls),
        'kickoff_index':int(bot.kickoff_index),
    }
    bot._v038c_count=n+1
    bot._v038c_buffer.append(r)
    if len(bot._v038c_buffer)>=32:flush(bot)


def capture(*args,**kwargs):
    # Telemetry must never make Nexto crash or lose its normal controls.
    return record(*args,**kwargs)
