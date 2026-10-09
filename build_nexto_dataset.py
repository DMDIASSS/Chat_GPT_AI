"""Label existing 1v1 replays with Nexto's pretrained policy.

Offline teacher distillation: observations are sampled from recorded HUMAN
states (not Nexto-controlled RocketSim rollouts). It is a useful bootstrap,
not a proof of Nexto-level skill or exact teacher behavior on rollouts.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from nexto_teacher import NextoTeacher, action_mapping, compress_teacher_probs

ROOT = Path(__file__).resolve().parent


def build_dataset(folder: Path, output: Path, every: int, max_samples: int, teacher_batch: int,
                  device: str, temperature: float, verbose: bool = False) -> int:
    from rlgym.rocket_league.action_parsers import LookupTableAction
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    from chatgpt_ai.env import make_obs

    files = sorted(folder.rglob('*.replay'))
    if not files:
        raise FileNotFoundError(f'No .replay files inside {folder}')

    lookup = LookupTableAction.make_lookup_table()
    mapping, errors = action_mapping(lookup)
    exact = int(np.count_nonzero(errors < 1e-6))
    print(f'Nexto 90-action -> RLGym {len(lookup)}-action mapping: {exact}/90 exact, '
          f'max weighted error {errors.max():.3f}', flush=True)
    if len(lookup) != 90:
        raise RuntimeError('Unexpected student action count; stop instead of using invalid labels')
    if exact < 60:
        raise RuntimeError('Large teacher/student action mismatch; investigate action mapping first')

    teacher = NextoTeacher(device=device, batch_size=teacher_batch)
    x, p, group = [], [], []
    waiting_obs, waiting_teacher, waiting_group = [], [], []

    def flush():
        if not waiting_obs:
            return
        logits = teacher.logits(waiting_teacher)
        targets = compress_teacher_probs(logits, mapping, len(lookup), temperature)
        for obs, target, replay_id in zip(waiting_obs, targets, waiting_group):
            x.append(obs)
            p.append(target.astype(np.float16))
            group.append(replay_id)
        waiting_obs.clear()
        waiting_teacher.clear()
        waiting_group.clear()

    for replay_id, path in enumerate(files):
        if len(x) + len(waiting_obs) >= max_samples:
            break
        added = 0
        try:
            replay = ParsedReplay.load(path)
            builder = make_obs()
            initialized = False
            prev = {}
            for frame_no, frame in enumerate(replay_to_rlgym(replay)):
                if len(x) + len(waiting_obs) >= max_samples:
                    break
                if frame_no % every != 0 or len(frame.state.cars) != 2:
                    continue
                state = frame.state
                agents = list(state.cars)
                if not initialized:
                    builder.reset(agents, state, {})
                    initialized = True
                student_obs = builder.build_obs(agents, state, {})
                teacher_obs = teacher.observe(state, prev)
                for agent, q, kv, mask in teacher_obs:
                    if len(x) + len(waiting_obs) >= max_samples:
                        break
                    obs = np.asarray(student_obs[agent], dtype=np.float32).reshape(-1)
                    if obs.shape != (92,) or not np.isfinite(obs).all():
                        continue
                    waiting_obs.append(obs)
                    waiting_teacher.append((q, kv, mask))
                    waiting_group.append(replay_id)
                    added += 1
                    if len(waiting_obs) >= teacher_batch:
                        flush()
                # For the next sampled frame's previous-action input, use
                # the observed human actions when available, not invented
                # Nexto closed-loop actions. This is an off-policy approximation.
                for agent in agents:
                    action = frame.actions.get(agent)
                    if action is not None:
                        arr = np.asarray(action, dtype=np.float32).reshape(-1)
                        if arr.shape == (8,) and np.isfinite(arr).all():
                            prev[agent] = arr
            flush()
            print(f'{path.name}: {added} teacher-labeled observations', flush=True)
        except Exception as exc:
            flush()
            print(f'{path.name}: FAILED: {type(exc).__name__}: {exc}', flush=True)
            if verbose:
                raise

    flush()
    if len(x) < 100:
        raise RuntimeError(f'Only {len(x)} samples produced. Need at least 100.')
    X = np.stack(x).astype(np.float32)
    P = np.stack(p).astype(np.float16)
    groups = np.asarray(group, dtype=np.int32)
    if X.shape[1] != 92 or P.shape[1] != 90 or not np.isfinite(X).all() or not np.isfinite(P).all():
        raise ValueError('Invalid dataset dimensions or nonfinite observations')
    if not np.allclose(P.astype(np.float32).sum(-1), 1., atol=2e-3):
        raise ValueError('Teacher probabilities did not sum to one')
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, obs=X, teacher_probs=P,
                        actions=P.argmax(1).astype(np.int64), replay_ids=groups)
    print(f'Saved {len(X):,} Nexto-labeled samples from {len(np.unique(groups))} replay files to {output}', flush=True)
    return len(X)


def main():
    ap = argparse.ArgumentParser(description='Generate Nexto-teacher dataset from 1v1 replays')
    ap.add_argument('--input', type=Path, default=ROOT / 'data/replays/ranked-duels')
    ap.add_argument('--output', type=Path, default=ROOT / 'data/datasets/nexto_teacher_1v1.npz')
    ap.add_argument('--every', type=int, default=8)
    ap.add_argument('--max-samples', type=int, default=150_000)
    ap.add_argument('--teacher-batch', type=int, default=256)
    ap.add_argument('--temperature', type=float, default=1.)
    ap.add_argument('--device', choices=['cpu', 'cuda:0'], default='cpu')
    ap.add_argument('--debug', action='store_true', help='Raise the first failed replay exception with traceback')
    a=ap.parse_args()
    if min(a.every,a.max_samples,a.teacher_batch) < 1 or a.temperature <= 0:
        ap.error('every/max-samples/teacher-batch must be positive, temperature > 0')
    build_dataset(a.input, a.output, a.every, a.max_samples,
                  a.teacher_batch, a.device, a.temperature, a.debug)

if __name__ == '__main__':
    main()
