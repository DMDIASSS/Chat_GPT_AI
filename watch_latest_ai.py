"""Watch the actual selected Chat GPT AI model play against a copy of itself.

Works with the project's 92-observation RLGym-PPO checkpoints, its distilled
students, and the original / fine-tuned Nexto attention policy. Inference only.

Requires the existing Chat_GPT_AI installation; place this in its root.
Nexto model and weights remain subject to upstream CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
import dataclasses
import random
import time
from pathlib import Path
from typing import Iterable

import numpy as np

ROOT = Path(__file__).resolve().parent


@dataclasses.dataclass(frozen=True)
class ModelChoice:
    family: str
    path: Path
    steps: int = 0

    @property
    def description(self) -> str:
        descriptions = {
            'ppo': '92-input PPO policy',
            'student': '92-input Nexto-distilled student',
            'bc': '92-input replay imitation policy',
            'native': 'fine-tuned ORIGINAL Nexto attention network',
            'nexto': 'unmodified original Nexto attention network',
            'smoke': 'old smoke PPO policy',
        }
        return descriptions[self.family]


def latest_ppo(root: Path, backup: bool = False) -> ModelChoice | None:
    folder = root / 'data' / 'checkpoints' / ('chat_gpt_ai_smoke_backup' if backup else 'chat_gpt_ai')
    candidates = list(folder.rglob('PPO_POLICY.pt')) if folder.exists() else []
    if not candidates:
        return None

    def score(p: Path):
        # PPO saves to numbered cumulative-step directories; prefer the highest
        # step count even when an old checkpoint was copied more recently.
        num = int(p.parent.name) if p.parent.name.isdecimal() else -1
        return num, p.stat().st_mtime_ns

    path = max(candidates, key=score)
    return ModelChoice('smoke' if backup else 'ppo', path,
                       int(path.parent.name) if path.parent.name.isdecimal() else 0)


def choices(root: Path) -> dict[str, ModelChoice]:
    result: dict[str, ModelChoice] = {}
    ppo = latest_ppo(root)
    if ppo:
        result['ppo'] = ppo
    smoke = latest_ppo(root, backup=True)
    if smoke:
        result['smoke'] = smoke
    student_dir = root / 'data'
    students = list(student_dir.glob('nexto_student*.pt')) if student_dir.is_dir() else []
    if students:
        # Works with V2 and future V3/V4 models. Choose latest modified.
        path = max(students, key=lambda p: p.stat().st_mtime_ns)
        result['student'] = ModelChoice('student', path)
    bc = root / 'data' / 'bc_policy.pt'
    if bc.is_file():
        result['bc'] = ModelChoice('bc', bc)
    native = root / 'data' / 'native_nexto' / 'last.pt'
    if native.is_file():
        result['native'] = ModelChoice('native', native)
    original = root / 'vendor' / 'nexto' / 'nexto-model.pt'
    if original.is_file():
        result['nexto'] = ModelChoice('nexto', original)
    return result


def choose_model(root: Path, family: str, checkpoint: str | None = None) -> ModelChoice:
    available = choices(root)
    if checkpoint:
        path = Path(checkpoint).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Explicit checkpoint does not exist: {path}')
        # For explicit files, the user must specify native to avoid trying to load
        # actor+optimizer state as a 92-input feed-forward state_dict.
        if family in ('auto', 'latest'):
            if path.name == 'last.pt' and path.parent.name == 'native_nexto':
                family = 'native'
            elif path.name == 'nexto-model.pt':
                family = 'nexto'
            else:
                family = 'ppo'
        return ModelChoice(family, path)
    if family in ('auto', 'latest'):
        trained = [available[f] for f in ('ppo', 'student', 'native') if f in available]
        if not trained:
            raise FileNotFoundError('No trained models found in data/. Run training or choose --model nexto.')
        # Comparing different families by steps is meaningless. Choose the most
        # recently modified trained file and SHOW it to the user before playback.
        return max(trained, key=lambda candidate: candidate.path.stat().st_mtime_ns)
    if family not in available:
        raise FileNotFoundError(f'Model family {family!r} unavailable. Use --list to inspect saved models.')
    return available[family]


def sample_action(probs, rng: np.random.Generator, mode: str) -> int:
    probabilities = np.asarray(probs, dtype=np.float64).reshape(-1)
    if probabilities.shape != (90,) or not np.all(np.isfinite(probabilities)):
        raise ValueError(f'Policy must return 90 finite probabilities; got {probabilities.shape}')
    if np.min(probabilities) < -1e-8:
        raise ValueError('Action probabilities cannot be negative')
    probabilities = probabilities.clip(0)
    total = probabilities.sum()
    if total <= 0:
        raise ValueError('Action probabilities sum to zero')
    probabilities /= total
    return int(np.argmax(probabilities)) if mode == 'greedy' else int(rng.choice(90, p=probabilities))


class FFController:
    """One shared 92-input neural network controlling both copies of the car."""
    def __init__(self, checkpoint: Path):
        from chatgpt_ai.policy import LoadedPolicy
        from chatgpt_ai.env import make_obs
        from rlgym.rocket_league.action_parsers import LookupTableAction
        self.policy = LoadedPolicy(checkpoint)
        if (self.policy.obs_count, self.policy.action_count) != (92, 90):
            raise ValueError('This viewer requires the original 92-input / 90-action FF policy')
        self.obs_builder = make_obs()
        self.table = np.asarray(LookupTableAction.make_lookup_table(), dtype=np.float32)
        if self.table.shape != (90, 8):
            raise ValueError('Unexpected RLGym action lookup table')

    def reset(self, state):
        self.obs_builder.reset(list(state.cars), state, {})

    def actions(self, state, previous: dict, mode: str, rng: np.random.Generator) -> dict:
        import torch
        obs = self.obs_builder.build_obs(list(state.cars), state, {})
        commands = {}
        with torch.inference_mode():
            for car_id in state.cars:
                x = np.asarray(obs[car_id], dtype=np.float32).reshape(-1)
                if len(x) != self.policy.obs_count:
                    raise ValueError(f'Observation mismatch: {len(x)} != {self.policy.obs_count}')
                output = self.policy.policy.get_output(x)
                chosen = sample_action(output.detach().cpu().numpy(), rng, mode)
                commands[car_id] = self.table[chosen].copy()
        return commands


class NativeController:
    """One shared original attention-based Nexto policy controlling both cars."""
    def __init__(self, choice: ModelChoice):
        import torch
        from nexto_teacher import NextoTeacher, nexto_actions
        self.torch = torch
        self.teacher = NextoTeacher('cpu')
        original = ROOT / 'vendor' / 'nexto' / 'nexto-model.pt'
        if not original.is_file():
            raise FileNotFoundError(f'Missing original Nexto weights at {original}')
        self.actor = torch.jit.load(str(original), map_location='cpu')
        if choice.family == 'native':
            state = torch.load(str(choice.path), map_location='cpu', weights_only=True)
            if not isinstance(state, dict) or 'actor' not in state:
                raise ValueError(f'Not a native actor checkpoint: {choice.path}')
            self.actor.load_state_dict(state['actor'], strict=True)
            print(f"  Native training decisions: {state.get('timesteps', 'unknown')}", flush=True)
        self.actor.eval()
        self.table = nexto_actions()
        if self.table.shape != (90, 8):
            raise ValueError('Unexpected Nexto action table')
        torch.set_num_threads(min(2, torch.get_num_threads()))

    def reset(self, state):
        # The original Nexto builder is stateless for a single current 1v1 frame;
        # previous actions are passed separately for each car every decision.
        pass

    def actions(self, state, previous: dict, mode: str, rng: np.random.Generator) -> dict:
        torch = self.torch
        views = self.teacher.observe(state, previous)
        qs = np.stack([v[1] for v in views])
        kvs = np.stack([v[2] for v in views])
        masks = np.stack([v[3] for v in views])
        with torch.inference_mode():
            logits, _ = self.actor((torch.from_numpy(qs), torch.from_numpy(kvs), torch.from_numpy(masks)))
            probabilities = torch.softmax(logits.float(), dim=-1).detach().cpu().numpy()
        commands = {}
        for (car_id, *_), probs in zip(views, probabilities):
            chosen = sample_action(probs, rng, mode)
            commands[car_id] = self.table[chosen].copy()
        return commands


def create_state(engine, start: str, rng: np.random.Generator):
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    base = engine.create_base_state()
    FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(base, {})
    if start == 'grounded':
        from chatgpt_ai.curriculum import ChatGPTCurriculum
        ChatGPTCurriculum('grounded').apply(base, {})
    else:
        KickoffMutator().apply(base, {})
    return engine.set_state(base, {})


def run_view(choice: ModelChoice, mode: str, start: str, speed: float,
             decisions: int, episodes: int, seed: int, show_every: int):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.rlviser import RLViserRenderer
    from rlgym.rocket_league.action_parsers import LookupTableAction

    # Match is 120 Hz physics with 8 ticks / decision => 15 decisions/s.
    rng = np.random.default_rng(seed)
    random.seed(seed)
    model = NativeController(choice) if choice.family in ('native', 'nexto') else FFController(choice.path)
    engine = RocketSimEngine(rlbot_delay=False)
    renderer = None
    score = {'blue': 0, 'orange': 0}
    cumulative = {'blue': 0, 'orange': 0}
    try:
        renderer = RLViserRenderer(tick_rate=15 * speed)
        print('\nCHOSEN MODEL:', choice.description, flush=True)
        print('CHECKPOINT:', choice.path.resolve(), flush=True)
        if choice.steps:
            print('PPO checkpoint steps:', f'{choice.steps:,}', flush=True)
        print('BLUE and ORANGE use the SAME weights (separate car observations).', flush=True)
        print('Mode:', mode, '| Start:', start, '| Playback:', speed, 'x', flush=True)
        print('Press Ctrl+C in this terminal to stop. Viewer uses RLViser camera controls.\n', flush=True)
        for ep in range(1, episodes + 1) if episodes > 0 else iter(int, 1):
            state = create_state(engine, start, rng)
            model.reset(state)
            previous = {}
            touch = {'blue': 0, 'orange': 0}
            winner = 'timeout'
            for tick in range(1, decisions + 1):
                frame_start = time.perf_counter()
                renderer.render(state, {})
                commands = model.actions(state, previous, mode, rng)
                if set(commands) != set(state.cars):
                    raise ValueError('Model must return exactly one action for each car')
                state = engine.step({car_id: np.tile(cmd, (8, 1)) for car_id, cmd in commands.items()}, {})
                previous = commands
                for car_id, car in state.cars.items():
                    key = 'orange' if car.is_orange else 'blue'
                    touched = int(getattr(car, 'ball_touches', 0))
                    touch[key] += touched
                    cumulative[key] += touched
                if getattr(state, 'goal_scored', False):
                    winner = 'blue' if float(state.ball.position[1]) > 0 else 'orange'
                    score[winner] += 1
                    renderer.render(state, {})
                    break
                if show_every > 0 and tick % show_every == 0:
                    print(f'Episode {ep} | t={tick/15:.1f}s | touches blue={touch["blue"]}, '
                          f'orange={touch["orange"]} | goals B:{score["blue"]} O:{score["orange"]}', flush=True)
                delay = 1.0 / (15.0 * speed) - (time.perf_counter() - frame_start)
                if delay > 0:
                    time.sleep(delay)
            print(f'Episode {ep} -> {winner} | touches blue={touch["blue"]}, '
                  f'orange={touch["orange"]} | cumulative goals {score}', flush=True)
        print('Finished. Total contacts:', cumulative, flush=True)
    except KeyboardInterrupt:
        print('\nViewer stopped by user.', flush=True)
    finally:
        if renderer is not None:
            renderer.close()
        engine.close()


def parse_args(argv: Iterable[str] | None = None):
    p = argparse.ArgumentParser(description='Watch latest Chat GPT AI model vs itself in RocketSim/RLViser')
    p.add_argument('--model', choices=['auto', 'ppo', 'student', 'native', 'nexto', 'bc', 'smoke'], default='auto',
                   help='auto chooses most recently modified trained file from PPO, student and native')
    p.add_argument('--checkpoint', type=str, default=None,
                   help='Explicit checkpoint path. Use --model native if pointing to native actor state.')
    p.add_argument('--list', action='store_true', help='List available saved models without opening a viewer')
    p.add_argument('--actions', choices=['sample', 'greedy'], default='sample')
    p.add_argument('--start', choices=['kickoff', 'grounded'], default='kickoff')
    p.add_argument('--speed', type=float, default=1.0)
    p.add_argument('--decisions', type=int, default=900, help='max decisions per episode; 15 = one simulated second')
    p.add_argument('--episodes', type=int, default=0, help='0 = loop until Ctrl+C')
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--show-every', type=int, default=150, help='print progress every N decisions; 0 = only episode ends')
    args = p.parse_args(argv)
    if args.speed <= 0 or args.decisions < 1 or args.episodes < 0 or args.show_every < 0:
        p.error('speed > 0, decisions >= 1, episodes >= 0, show-every >= 0 required')
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.list:
        print('Available Chat GPT AI models:')
        available = choices(ROOT)
        if not available:
            print('  None found. Check your project folder.')
        for name, item in available.items():
            print(f'  {name:8} | {item.path} | steps={item.steps:,} | modified={time.ctime(item.path.stat().st_mtime)}')
        if any(name in available for name in ('ppo', 'student', 'native')):
            picked = choose_model(ROOT, 'auto')
            print('\nAUTO WOULD SELECT:', picked.family, picked.path)
        return
    selected = choose_model(ROOT, args.model, args.checkpoint)
    # Printed BEFORE importing viewer dependencies, so even a missing DLL
    # cannot obscure which model was selected.
    print('SELECTED FAMILY:', selected.family, flush=True)
    print('SELECTED CHECKPOINT:', selected.path.resolve(), flush=True)
    run_view(selected, args.actions, args.start, args.speed, args.decisions,
             args.episodes, args.seed, args.show_every)


if __name__ == '__main__':
    main()
