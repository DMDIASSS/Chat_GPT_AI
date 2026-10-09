"""Compare native Nexto checkpoints using outcome AND useful-touch proxies.

Run next to native_nexto.py, nexto_teacher.py, and vendor/nexto/nexto-model.pt.
Does NOT train models or change checkpoints. Offline RocketSim only.
"""
from __future__ import annotations
import argparse
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch

from nexto_teacher import NextoTeacher, nexto_actions
from native_nexto import Match, actor_logits, unpack_obs

ROOT = Path(__file__).resolve().parent
DT = 8 / 120  # seconds between policy decisions (RocketSim 120 Hz, action repeat 8)


def relative_values(state, car_id):
    car = state.cars[car_id]
    cp = np.asarray(car.physics.position, dtype=float)
    cv = np.asarray(car.physics.linear_velocity, dtype=float)
    bp = np.asarray(state.ball.position, dtype=float)
    bv = np.asarray(state.ball.linear_velocity, dtype=float)
    return float(np.linalg.norm(cp - bp)), float(np.linalg.norm(cv - bv)), bp, bv


def forward_y(orange):
    return -1.0 if orange else 1.0


def is_controlled_ball(state, car_id, last_touch):
    """Conservative possession proxy, not ground-truth human-style possession.

    Own team has last touch; ball near our car and matching its velocity while low.
    """
    if last_touch != car_id:
        return False
    dist, rel_speed, bp, _ = relative_values(state, car_id)
    return dist < 450.0 and rel_speed < 650.0 and bp[2] < 350.0


def evaluate_touch(before, after, our_id, orange):
    """Return (productive, dangerous) based on ball directional momentum *change*.

    Not a shot model. This deliberately avoids rewarding touches just for contact.
    """
    if int(getattr(after.cars[our_id], 'ball_touches', 0)) <= 0:
        return (False, False)
    s = forward_y(orange)
    v0 = s * float(before.ball.linear_velocity[1])
    v1 = s * float(after.ball.linear_velocity[1])
    return (v1 >= 450.0 and v1 - v0 >= 150.0,
            v1 <= -450.0 and v1 - v0 <= -150.0)


class GameMetrics:
    def __init__(self, our_id, opp_id, our_orange):
        self.ours, self.opp, self.orange = our_id, opp_id, our_orange
        self.ticks = 0
        self.touch = Counter()
        self.productive = Counter()
        self.dangerous = Counter()
        self.controls = {"ours": Counter(), "nexto": Counter()}
        self.last_touch = None
        self.control_ticks = Counter()
        self.control_run = Counter()
        self.control_episodes = Counter()
        self.offensive_half_ticks = Counter()
        self.defensive_threat_ticks = Counter()

    def record(self, before, after, our_action, nexto_action):
        self.ticks += 1
        action_table = nexto_actions()
        for key, action_id in (("ours", our_action), ("nexto", nexto_action)):
            action = action_table[int(action_id)]
            for label, index, present in (("jump", 5, action[5] > 0),
                                          ("boost", 6, action[6] > 0),
                                          ("handbrake", 7, action[7] > 0),
                                          ("forward_throttle", 0, action[0] > 0)):
                if present:
                    self.controls[key][label] += 1
        for key, agent, orange in (("ours", self.ours, self.orange),
                                   ("nexto", self.opp, not self.orange)):
            touches = int(getattr(after.cars[agent], 'ball_touches', 0))
            if touches:
                self.touch[key] += touches
                good, bad = evaluate_touch(before, after, agent, orange)
                if good:
                    self.productive[key] += 1
                if bad:
                    self.dangerous[key] += 1
                self.last_touch = agent  # approximate ordering if both touch same decision

        # Last touch may be ambiguous for simultaneous touches; don't claim control then.
        if (getattr(after.cars[self.ours], 'ball_touches', 0)
                and getattr(after.cars[self.opp], 'ball_touches', 0)):
            self.last_touch = None
        by = float(after.ball.position[1])
        bvy = float(after.ball.linear_velocity[1])
        bx = float(after.ball.position[0])
        for key, agent, orange in (("ours", self.ours, self.orange),
                                   ("nexto", self.opp, not self.orange)):
            s = forward_y(orange)
            if s * by > 0:
                self.offensive_half_ticks[key] += 1
            if s * by < -2800 and s * bvy < -450 and abs(bx) < 1800:
                self.defensive_threat_ticks[key] += 1
            if is_controlled_ball(after, agent, self.last_touch):
                self.control_ticks[key] += 1
                self.control_run[key] += 1
            else:
                if self.control_run[key] >= 8:  # >= about 0.53 seconds
                    self.control_episodes[key] += 1
                self.control_run[key] = 0

    def summary(self):
        for key in ("ours", "nexto"):
            if self.control_run[key] >= 8:
                self.control_episodes[key] += 1
            self.control_run[key] = 0
        return {
            "ticks": self.ticks,
            "touches": dict(self.touch),
            "productive_touches": dict(self.productive),
            "dangerous_touches": dict(self.dangerous),
            "controlled_ball_ticks": dict(self.control_ticks),
            "controlled_sequences_0_53s": dict(self.control_episodes),
            "offensive_half_ticks": dict(self.offensive_half_ticks),
            "defensive_threat_ticks": dict(self.defensive_threat_ticks),
            "action_ticks": {k: dict(v) for k, v in self.controls.items()},
        }


def infer(actor, view):
    q, kv, mask = unpack_obs(view, 'cpu')
    with torch.inference_mode():
        return int(actor_logits(actor, q, kv, mask).argmax(-1).item())


def score_summaries(summaries):
    total = sum(int(s['ticks']) for s in summaries)
    keys = ("ours", "nexto")
    counts = {name: {k: sum(int(s[name].get(k, 0)) for s in summaries)
                     for k in keys}
              for name in ("touches", "productive_touches", "dangerous_touches",
                           "controlled_ball_ticks", "controlled_sequences_0_53s",
                           "offensive_half_ticks", "defensive_threat_ticks")}
    action_counts = {k: {act: sum(int(s['action_ticks'].get(k, {}).get(act, 0)) for s in summaries)
                         for act in ("jump", "boost", "handbrake", "forward_throttle")}
                     for k in keys}
    result = {"total_decision_ticks": total, "total_seconds": round(total * DT, 2),
              "raw": counts, "controls": action_counts, "rates": {}}
    for key in keys:
        touches = max(1, counts['touches'][key])
        result['rates'][key] = {
            "touches_per_1000_ticks": round(counts['touches'][key] * 1000 / max(1, total), 2),
            "productive_touches_pct": round(100 * counts['productive_touches'][key] / touches, 2),
            "dangerous_touches_pct": round(100 * counts['dangerous_touches'][key] / touches, 2),
            "controlled_ball_seconds": round(counts['controlled_ball_ticks'][key] * DT, 2),
            "controlled_ball_time_pct": round(100 * counts['controlled_ball_ticks'][key] / max(1, total), 2),
            "controlled_sequences": counts['controlled_sequences_0_53s'][key],
            "offensive_half_time_pct": round(100 * counts['offensive_half_ticks'][key] / max(1, total), 2),
            "defensive_threat_time_pct": round(100 * counts['defensive_threat_ticks'][key] / max(1, total), 2),
            "jump_action_pct": round(100 * action_counts[key]['jump'] / max(1, total), 2),
            "boost_action_pct": round(100 * action_counts[key]['boost'] / max(1, total), 2),
            "handbrake_action_pct": round(100 * action_counts[key]['handbrake'] / max(1, total), 2),
        }
    return result


def run_eval(name, actor, teacher, *, games, decisions, seed, scenarios):
    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=False)
    scores = Counter()
    summaries = []
    actor.eval()
    try:
        for i in range(games):
            # Reset seeds for paired comparisons of the ORIGINAL and TUNED actor.
            random.seed(seed + 1009 * i)
            np.random.seed((seed + 1009 * i) % (2**32))
            match = Match(teacher, engine, training_side_orange=bool(i % 2), scenarios=scenarios)
            metrics = GameMetrics(match.ours, match.opponent, match.our_orange)
            winner = 'draw'
            for _ in range(decisions):
                our_view, opp_view = match.observe()
                our_action = infer(actor, our_view)
                nexto_action = int(teacher.logits([(opp_view[1], opp_view[2], opp_view[3])])[0].argmax())
                previous_state = SimpleNamespace(ball=SimpleNamespace(
                    linear_velocity=np.asarray(match.state.ball.linear_velocity, dtype=float).copy()))
                _, done, winner = match.step(our_action, nexto_action, decisions)
                metrics.record(previous_state, match.state, our_action, nexto_action)
                if done:
                    break
            scores[winner] += 1
            report = metrics.summary()
            report['winner'] = winner
            report['side'] = 'orange' if match.our_orange else 'blue'
            summaries.append(report)
            print(f'{name}: {i+1}/{games} | {winner} | touches '
                  f'{report["touches"].get("ours", 0)}:{report["touches"].get("nexto", 0)}', flush=True)
    finally:
        engine.close()
    return {'name': name, 'scores': dict(scores), 'episodes': summaries,
            'aggregate': score_summaries(summaries)}


def main():
    p = argparse.ArgumentParser(description='Offline quality metrics: ORIGINAL / TUNED Nexto vs frozen Nexto')
    p.add_argument('--checkpoint', type=Path, default=Path('data/native_nexto/last.pt'))
    p.add_argument('--games', type=int, default=20)
    p.add_argument('--episode-decisions', type=int, default=750)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--scenarios', choices=['kickoff', 'grounded'], default='kickoff')
    p.add_argument('--output', type=Path, default=None)
    args = p.parse_args()
    if args.games < 2 or args.games % 2 or args.episode_decisions < 1:
        p.error('--games must be a positive even number >=2 and --episode-decisions >=1')
    if not args.checkpoint.is_file():
        p.error(f'Checkpoint missing: {args.checkpoint}')
    torch.set_num_threads(2)
    teacher = NextoTeacher('cpu')
    original = torch.jit.load(str(Path('vendor/nexto/nexto-model.pt')), map_location='cpu')
    original.eval()
    tuned = torch.jit.load(str(Path('vendor/nexto/nexto-model.pt')), map_location='cpu')
    weights = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    tuned.load_state_dict(weights['actor'], strict=True)
    tuned.eval()
    print(f'Tuned checkpoint: {args.checkpoint} | decisions trained: {weights.get("timesteps", "unknown")}', flush=True)
    report = {'benchmark': 'first-to-score', 'scripted_kickoff': False,
              'note': 'Controlled-ball, threatening-ball and productive-touch metrics are heuristic proxies, NOT ground-truth possession/xG.',
              'args': vars(args), 'models': []}
    report['args']['checkpoint'] = str(args.checkpoint)
    report['args']['output'] = str(args.output) if args.output is not None else None
    for name, model in (('original', original), ('tuned', tuned)):
        r = run_eval(name, model, teacher, games=args.games, decisions=args.episode_decisions,
                     seed=args.seed, scenarios=args.scenarios)
        report['models'].append(r)
        print('\n', name, 'outcomes:', r['scores'])
        for side, values in r['aggregate']['rates'].items():
            print(f' {side}: {values}')
    output = args.output or Path('data/evaluations') / f'native_quality_{datetime.now():%Y%m%d_%H%M%S}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'\nSaved report: {output.resolve()}')
    print('Compare goals and productive/control metrics. More raw touches alone do NOT prove improvement.')


if __name__ == '__main__':
    main()
