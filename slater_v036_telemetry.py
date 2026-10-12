"""Read-only RLBot-v4 kickoff telemetry. Copied into each Nexto mode's folder.

Errors inside telemetry are handled by the bot.py wrapper; this module only
reads game packets and writes bounded, unique per-process JSONL logs.
"""
import json
import os
import time
import uuid
from pathlib import Path


def _get_xyz(obj):
    return [float(getattr(obj, k)) for k in ('x', 'y', 'z')]


def _score(packet):
    teams = getattr(packet, 'teams', ())
    try:
        if len(teams) >= 2:
            return [int(teams[0].score), int(teams[1].score)]
    except (AttributeError, TypeError):
        pass
    return None


def _write(bot, value):
    path = bot._v036_log
    # Exclusive creation on first write; never overwrite a previous run.
    if not bot._v036_log_created:
        with path.open('x', encoding='utf8') as f:
            f.write(json.dumps({'type': 'metadata', 'mode': bot._v036_mode,
                                'team': int(bot.team), 'index': int(bot.index),
                                'wall_time': time.time(), 'schema': 1}) + '\n')
        bot._v036_log_created = True
        print('SLATER_V036_KICKOFF_LOG', path, flush=True)
    with path.open('a', encoding='utf8') as f:
        f.write(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')


def note(bot, packet, mode):
    if not hasattr(bot, '_v036_log'):
        bot._v036_mode = mode
        bot._v036_log = (Path(__file__).resolve().parent / 'kickoff_logs_v036' /
                         ('v036_' + mode.lower() + '_' + uuid.uuid4().hex + '.jsonl'))
        bot._v036_log.parent.mkdir(parents=True, exist_ok=True)
        bot._v036_log_created = False
        bot._v036_calls = 0
        bot._v036_last_pause = False
        bot._v036_start_time = None
        bot._v036_touch_baseline = -1e9
        bot._v036_touched = False
        bot._v036_last_score = None
        bot._v036_match_end = False
        bot._v036_kickoff_id = 0
    bot._v036_calls += 1
    gi = packet.game_info
    t = float(gi.seconds_elapsed)
    pause = bool(gi.is_kickoff_pause)
    score = _score(packet)
    if score is not None and bot._v036_last_score is not None and score != bot._v036_last_score:
        _write(bot, {'type': 'score_change', 't': t, 'score': score,
                     'previous_score': bot._v036_last_score, 'kickoff': bot._v036_kickoff_id})
    if score is not None:
        bot._v036_last_score = score
    touch = getattr(packet.game_ball, 'latest_touch', None)
    touch_t = float(getattr(touch, 'time_seconds', -1e9)) if touch is not None else -1e9
    if pause and not bot._v036_last_pause:
        bot._v036_kickoff_id += 1
        bot._v036_start_time = t
        bot._v036_touch_baseline = touch_t
        bot._v036_touched = False
        _write(bot, {'type': 'kickoff_start', 't': t, 'kickoff': bot._v036_kickoff_id,
                     'score': score})
    bot._v036_last_pause = pause
    active = bot._v036_start_time is not None and t >= bot._v036_start_time and t - bot._v036_start_time <= 5.0
    if active and not bot._v036_touched and touch_t > bot._v036_touch_baseline + 1e-4 and touch_t >= bot._v036_start_time - .1:
        bot._v036_touched = True
        _write(bot, {'type': 'first_touch', 't': t, 'touch_time': touch_t,
                     'player_index': int(getattr(touch, 'player_index', -1)),
                     'kickoff': bot._v036_kickoff_id})
    # Log only every ~8 callbacks (normal 120Hz -> ~15Hz), and only within kickoff windows.
    if active and bot._v036_calls % 8 == 0:
        ball = packet.game_ball.physics
        car = packet.game_cars[bot.index]
        _write(bot, {'type': 'snapshot', 't': t, 'kickoff': bot._v036_kickoff_id,
                     'pause': pause, 'score': score,
                     'ball_pos': _get_xyz(ball.location),
                     'ball_vel': _get_xyz(ball.velocity),
                     'car_pos': _get_xyz(car.physics.location),
                     'car_vel': _get_xyz(car.physics.velocity),
                     'boost': float(car.boost),
                     'action': [float(getattr(bot.controls, k)) for k in
                                ('throttle', 'steer', 'pitch', 'yaw', 'roll')] +
                               [int(bool(getattr(bot.controls, k))) for k in
                                ('jump', 'boost', 'handbrake')]})
    if bool(getattr(gi, 'is_match_ended', False)) and not bot._v036_match_end:
        bot._v036_match_end = True
        _write(bot, {'type': 'match_end', 't': t, 'score': score, 'kickoffs': bot._v036_kickoff_id})
