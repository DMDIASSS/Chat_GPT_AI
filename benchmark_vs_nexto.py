"""First-to-score RocketSim evaluation: student vs Nexto's LEARNED policy.

Not a complete timed Rocket League match, and not the RLBot Nexto scripted
kickoff controller. Side swaps and fixed seeds enable repeatable comparisons.
Set --render to watch in RLViser (requires `rlgym[rl-rlviser]` and RLViser).
"""
from __future__ import annotations
import argparse
import random
import time
from pathlib import Path

import numpy as np
from nexto_teacher import NextoTeacher, nexto_actions


def first_goal_owner(ball_y: float, student_orange: bool) -> str:
    # Blue scores in +Y, Orange scores in -Y. Avoid giving a kickoff bounce
    # to the wrong side; only call this after RocketSim reports a goal.
    blue_scored = ball_y > 0
    return 'student' if blue_scored != student_orange else 'nexto'


def main():
    p = argparse.ArgumentParser(description='RocketSim first-goal episodes versus Nexto policy')
    p.add_argument('--checkpoint', type=Path, default=None)
    p.add_argument('--games', type=int, default=20)
    p.add_argument('--episode-decisions', type=int, default=750)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--render', action='store_true', help='Visualize with RLViser at 15 decisions/second')
    p.add_argument('--speed', type=float, default=1.0, help='Viewer playback speed; 1 is real-time')
    a = p.parse_args()
    if a.games < 1 or a.episode_decisions < 1 or a.speed <= 0:
        p.error('Games, episode decisions, speed must be positive')
    random.seed(a.seed)
    np.random.seed(a.seed)

    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    from chatgpt_ai.env import make_obs
    from chatgpt_ai.policy import LoadedPolicy

    teacher = NextoTeacher('cpu')
    student = LoadedPolicy(a.checkpoint)
    table = np.asarray(LookupTableAction.make_lookup_table(), dtype=np.float32)
    teacher_table = nexto_actions()
    if student.obs_count != 92 or student.action_count != len(table):
        raise ValueError('Checkpoint incompatible with the 92-input, 90-action benchmark')
    if table.shape != (90, 8) or not np.array_equal(table, teacher_table):
        raise ValueError('Nexto and student action tables differ. Stop and investigate.')
    print(f'Student checkpoint: {student.path}', flush=True)
    print('Opponent: Nexto TorchScript learned policy, NO RLBot scripted kickoff.', flush=True)

    renderer = None
    if a.render:
        try:
            from rlgym.rocket_league.rlviser import RLViserRenderer
            renderer = RLViserRenderer(tick_rate=15 * a.speed)
        except ImportError as exc:
            raise RuntimeError('Install viewer requirements: python -m pip install "rlgym[rl-rlviser]"') from exc

    engine = RocketSimEngine(rlbot_delay=False)
    outcomes = {'student': 0, 'nexto': 0, 'draw': 0}
    touches = {'student': 0, 'nexto': 0}
    first_touch_decisions = []
    try:
        for game in range(a.games):
            base = engine.create_base_state()
            FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(base, {})
            KickoffMutator().apply(base, {})
            state = engine.set_state(base, {})
            builder = make_obs()
            builder.reset(list(state.cars), state, {})
            prev = {}
            student_orange = bool(game % 2)
            student_agent = next(k for k in state.cars if bool(state.cars[k].is_orange) == student_orange)
            nexto_agent = next(k for k in state.cars if k != student_agent)
            outcome = 'draw'
            first_touch = None
            for decision in range(a.episode_decisions):
                started = time.perf_counter()
                if renderer is not None:
                    renderer.render(state, {})
                obs = builder.build_obs(list(state.cars), state, {})
                student_id = int(student.act(obs[student_agent])[0])
                student_control = table[student_id]
                teacher_obs = teacher.observe(state, prev)
                view = next(v for v in teacher_obs if v[0] == nexto_agent)
                logits = teacher.logits([(view[1], view[2], view[3])])
                nexto_control = teacher_table[int(logits[0].argmax())]
                prev = {nexto_agent: nexto_control, student_agent: student_control}
                actions = {
                    student_agent: np.tile(student_control, (8, 1)),
                    nexto_agent: np.tile(nexto_control, (8, 1)),
                }
                state = engine.step(actions, {})
                st = int(getattr(state.cars[student_agent], 'ball_touches', 0))
                nt = int(getattr(state.cars[nexto_agent], 'ball_touches', 0))
                touches['student'] += st
                touches['nexto'] += nt
                if first_touch is None and (st or nt):
                    first_touch = decision + 1
                if getattr(state, 'goal_scored', False):
                    outcome = first_goal_owner(float(state.ball.position[1]), student_orange)
                    break
                if renderer is not None:
                    delay = (1.0 / (15 * a.speed)) - (time.perf_counter() - started)
                    if delay > 0:
                        time.sleep(delay)
            outcomes[outcome] += 1
            if first_touch is not None:
                first_touch_decisions.append(first_touch)
            print(f'Episode {game+1}/{a.games}: {outcome}; first touch tick={first_touch or "none"}', flush=True)
    finally:
        try:
            if renderer is not None:
                renderer.close()
        finally:
            engine.close()

    print('\nRESULTS — first-to-score episodes, Nexto learned policy ONLY')
    print(f'Student first goals: {outcomes["student"]}/{a.games} ({outcomes["student"]/a.games:.1%})')
    print(f'Nexto first goals:   {outcomes["nexto"]}/{a.games} ({outcomes["nexto"]/a.games:.1%})')
    print(f'No goal episodes:    {outcomes["draw"]}/{a.games} ({outcomes["draw"]/a.games:.1%})')
    print(f'Total ball contact events: {touches}')
    if first_touch_decisions:
        print(f'Average decision ticks until first touch: {np.mean(first_touch_decisions):.1f}')
    print('This is NOT a full match win rate. Compare with same --seed, --games and --episode-decisions.')


if __name__ == '__main__':
    main()
