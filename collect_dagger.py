"""DAgger data collection: Nexto labels states reached by an imperfect student.

Requirements: existing Chat GPT AI + Nexto Fast Track add-on, RLGym v2 and RocketSim.
No reward optimization / no online ranked play. This collector only writes new NPZ shards.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np

from nexto_teacher import NextoTeacher, action_mapping, compress_teacher_probs, nexto_actions

ROOT = Path(__file__).resolve().parent


def find_new_shard(path: Path) -> int:
    found = []
    for item in path.glob('nexto_rollout_*.npz'):
        suffix = item.stem.rsplit('_', 1)[-1]
        if suffix.isdigit():
            found.append(int(suffix))
    return max(found, default=-1) + 1


def choose_student_control(student_action: int, teacher_action: int, teacher_probability: float,
                           rng: np.random.Generator) -> tuple[int, bool]:
    teacher_controlled = bool(rng.random() < teacher_probability)
    return (teacher_action if teacher_controlled else student_action), teacher_controlled


def run(args):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from chatgpt_ai.env import make_obs
    from chatgpt_ai.policy import LoadedPolicy

    if args.scenarios == 'grounded':
        from chatgpt_ai.curriculum import ChatGPTCurriculum
        scenario = ChatGPTCurriculum('grounded')
    else:
        scenario = KickoffMutator()

    table = np.asarray(LookupTableAction.make_lookup_table(), dtype=np.float32)
    if table.shape != (90, 8) or not np.array_equal(table, nexto_actions()):
        raise RuntimeError('Teacher and student action lookup tables differ; aborting')
    mapping, errors = action_mapping(table)
    if not np.all(errors < 1e-6):
        raise RuntimeError('Teacher and student action mapping is not exact')

    student = LoadedPolicy(args.checkpoint)
    if (student.obs_count, student.action_count) != (92, 90):
        raise RuntimeError('Student checkpoint shape must be 92 -> 90')
    teacher = NextoTeacher(args.teacher_device)
    engine = RocketSimEngine(rlbot_delay=False)
    mutator = FixedTeamSizeMutator(blue_size=1, orange_size=1)
    rng = np.random.default_rng(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    shard = find_new_shard(args.output)
    # Unique across script invocations using the next free shard ID.
    group_base = (shard + 1) * 1_000_000
    obs_rows, prob_rows, groups = [], [], []
    saved = 0
    episode = 0
    steps_in_episode = 0
    held_by_teacher = 0
    student_actions = 0
    touch_student = 0
    touch_opponent = 0
    prev = {}
    state = None
    obs_builder = None
    student_id = None
    opponent_id = None

    def save():
        nonlocal shard, saved
        if not obs_rows:
            return
        observations = np.asarray(obs_rows, dtype=np.float32)
        probabilities = np.asarray(prob_rows, dtype=np.float16)
        episode_ids = np.asarray(groups, dtype=np.int64)
        if observations.ndim != 2 or observations.shape[1] != 92 or probabilities.shape != (len(observations), 90):
            raise RuntimeError('Invalid DAgger dataset shape')
        if not np.isfinite(observations).all() or not np.isfinite(probabilities).all():
            raise RuntimeError('Nonfinite samples; nothing saved')
        if not np.allclose(probabilities.astype(np.float32).sum(axis=1), 1, atol=3e-3):
            raise RuntimeError('Teacher probabilities are not normalized')
        target = args.output / f'nexto_rollout_{shard:05d}.npz'
        if target.exists():
            raise FileExistsError(target)
        np.savez_compressed(target, obs=observations, teacher_probs=probabilities,
                            actions=probabilities.argmax(axis=1).astype(np.int64),
                            replay_ids=episode_ids)
        saved += len(observations)
        print(f'Saved DAgger shard: {target.name} ({len(observations):,} samples)', flush=True)
        shard += 1
        obs_rows.clear()
        prob_rows.clear()
        groups.clear()

    def reset():
        nonlocal episode, steps_in_episode, prev, state, obs_builder, student_id, opponent_id
        episode += 1
        steps_in_episode = 0
        prev = {}
        base = engine.create_base_state()
        mutator.apply(base, {})
        scenario.apply(base, {})
        state = engine.set_state(base, {})
        obs_builder = make_obs()
        obs_builder.reset(list(state.cars), state, {})
        orange = episode % 2 == 0
        student_id = next(k for k, c in state.cars.items() if bool(c.is_orange) == orange)
        opponent_id = next(k for k in state.cars if k != student_id)

    try:
        reset()
        for step in range(args.decisions):
            if steps_in_episode >= args.episode_decisions or getattr(state, 'goal_scored', False):
                reset()
            views = teacher.observe(state, prev)
            logits = teacher.logits([(q, kv, mask) for _, q, kv, mask in views])
            teacher_probabilities = compress_teacher_probs(logits, mapping, len(table), args.temperature)
            nexto_indices = {agent: int(logits[i].argmax()) for i, (agent, _, _, _) in enumerate(views)}
            teacher_probs_by_agent = {agent: teacher_probabilities[i] for i, (agent, _, _, _) in enumerate(views)}
            student_obs = np.asarray(obs_builder.build_obs(list(state.cars), state, {})[student_id], dtype=np.float32).reshape(-1)
            if student_obs.shape != (92,) or not np.isfinite(student_obs).all():
                raise ValueError(f'Invalid student observation {student_obs.shape}')
            student_action = int(student.act(student_obs)[0])
            chosen_action, teacher_used = choose_student_control(student_action, nexto_indices[student_id],
                                                                  args.teacher_probability, rng)
            held_by_teacher += int(teacher_used)
            student_actions += int(not teacher_used)
            current_student_control = table[chosen_action]
            current_opponent_control = table[nexto_indices[opponent_id]]
            # The target is what NEXT0 would have done in the STUDENT's actual state,
            # even when the student chooses its own incorrect control.
            obs_rows.append(student_obs)
            prob_rows.append(teacher_probs_by_agent[student_id])
            groups.append(group_base + episode)
            prev = {student_id: current_student_control, opponent_id: current_opponent_control}
            state = engine.step({
                student_id: np.tile(current_student_control, (8, 1)),
                opponent_id: np.tile(current_opponent_control, (8, 1)),
            }, {})
            touch_student += int(getattr(state.cars[student_id], 'ball_touches', 0))
            touch_opponent += int(getattr(state.cars[opponent_id], 'ball_touches', 0))
            steps_in_episode += 1
            if len(obs_rows) >= args.save_every:
                save()
            if (step + 1) % 1000 == 0:
                print(f'DAgger decisions {step + 1:,}/{args.decisions:,} | teacher-controlled={held_by_teacher:,} '
                      f'| student-controlled={student_actions:,} | contacts student={touch_student} nexto={touch_opponent}',
                      flush=True)
    finally:
        try:
            save()
        finally:
            engine.close()
    print(f'DAgger complete. New samples: {saved:,}; student-controlled decisions: {student_actions:,}.', flush=True)


def main():
    p = argparse.ArgumentParser(description='Collect Nexto correction labels on student-driven RocketSim states')
    p.add_argument('--checkpoint', type=Path, default=ROOT / 'data/nexto_student_policy.pt')
    p.add_argument('--output', type=Path, default=ROOT / 'data/datasets/nexto_rollouts')
    p.add_argument('--decisions', type=int, default=15_000)
    p.add_argument('--episode-decisions', type=int, default=450)
    p.add_argument('--save-every', type=int, default=5_000)
    p.add_argument('--teacher-probability', type=float, default=.5)
    p.add_argument('--temperature', type=float, default=1.)
    p.add_argument('--scenarios', choices=['grounded', 'kickoff'], default='grounded')
    p.add_argument('--seed', type=int, default=90210)
    p.add_argument('--teacher-device', choices=['cpu', 'cuda:0'], default='cpu')
    a = p.parse_args()
    if a.decisions < 1 or a.save_every < 1 or a.episode_decisions < 1 or a.temperature <= 0:
        p.error('Steps and temperature must be positive')
    if not 0 <= a.teacher_probability <= 1:
        p.error('--teacher-probability must be between 0 and 1')
    run(a)


if __name__ == '__main__':
    main()
