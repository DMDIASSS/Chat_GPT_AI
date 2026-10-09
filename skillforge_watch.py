"""Replay SkillForge's REAL saved action macros in RocketSim + RLViser.

This is not training and doesn't read or change Nexto weights.
Replays the exact parameters recorded in skillforge_search.py's discovery.json
or search_progress.json, using the same scenario builder and one physics tick
per action. Produces readable event logs and per-tick CSV for debugging.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from skillforge_core import Simulator, WavedashDetector, ZERO, macro_control

ROOT = Path(__file__).resolve().parent
DEFAULT_FOLDER = ROOT / 'data' / 'skillforge' / 'wavedash'
FIELDS = ('trial', 'label', 'tick', 'seconds', 'z', 'forward_speed', 'speed_gain',
          'vertical_speed', 'up_z', 'angular_speed', 'pitch', 'yaw', 'roll',
          'jump', 'grounded', 'has_flip', 'has_flipped', 'is_flipping',
          'flip_time', 'detected_dodge', 'landed_during_dodge', 'wheels_down',
          'success', 'reason')


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f'No search data at {path}. Run SF_1_SEARCH_REAL_WAVEDASH.bat first.')
    return json.loads(path.read_text(encoding='utf-8'))


def attempts(mode: str, folder: Path, requested_seed: int | None, generation: int | None):
    """Return labelled candidates; progress is generation best, not global best."""
    if mode in ('best', 'progress', 'generation'):
        data = read_json(folder / 'discovery.json')
        variant = str(data.get('variant', 'forward'))
        difficulty = str(data.get('difficulty', 'near'))
        train_seeds = data.get('training_seeds', [])
        seed = int(requested_seed if requested_seed is not None else (train_seeds[0] if train_seeds else 700))
        if mode == 'best':
            return [(f'GLOBAL BEST (unverified) seed={seed}', dict(data['candidate']), variant, difficulty, seed)]
        if mode == 'generation':
            gens = data.get('history', [])
            if generation is None or not 1 <= generation <= len(gens):
                raise ValueError(f'Generation must be in range 1..{len(gens)}')
            g = gens[generation - 1]
            return [(f'GEN {generation} fitness={g["highest_score"]}',
                    dict(g['candidate']), variant, difficulty, seed)]
        gens = data.get('history', [])
        if not gens:
            raise ValueError('No search generations found in discovery.json')
        return [(f'GEN {g["generation"]} fitness={g["highest_score"]}',
                dict(g['candidate']), variant, difficulty, seed) for g in gens]
    seed = int(requested_seed if requested_seed is not None else 700)
    if mode == 'idle':
        return [(f'NO INPUT seed={seed}', None, 'forward', 'near', seed)]
    if mode == 'dodge':
        return [(f'IMMEDIATE DODGE seed={seed}',
                 {'delay': 0, 'hold': 1, 'cancel_delay': 0, 'cancel_ticks': 12,
                  'pre': 0., 'post': 0., 'direction': -1.}, 'forward', 'near', seed)]
    raise ValueError(f'Unexpected mode {mode!r}')


def build_row(label, trial, tick, state, sim, detector, action):
    c = state.cars[sim.ours]
    v = np.asarray(c.physics.linear_velocity, dtype=np.float64)
    omega = np.asarray(c.physics.angular_velocity, dtype=np.float64)
    m = detector.metrics
    return dict(trial=trial, label=label, tick=tick, seconds=round(tick / 120, 4),
                z=round(float(c.physics.position[2]), 2),
                forward_speed=round(float(np.dot(v, sim.forward)), 2),
                speed_gain=round(float(m.speed_gain), 2),
                vertical_speed=round(float(v[2]), 2),
                up_z=round(float(c.physics.rotation_mtx[2, 2]), 3),
                angular_speed=round(float(np.linalg.norm(omega)), 3),
                pitch=round(float(action[2]), 2), yaw=round(float(action[3]), 2),
                roll=round(float(action[4]), 2), jump=int(action[5] > 0.5),
                grounded=int(bool(c.on_ground)), has_flip=int(bool(c.has_flip)),
                has_flipped=int(bool(c.has_flipped)), is_flipping=int(bool(c.is_flipping)),
                flip_time=round(float(c.flip_time), 4),
                detected_dodge=int(m.dodge_detected),
                landed_during_dodge=int(m.landed_during_dodge),
                wheels_down=int(m.wheels_down), success=int(m.success), reason=m.reason)


def render_trial(sim, renderer, *, label, params, variant, difficulty, seed,
                 trial, writer, max_ticks, speed, frame_skip, pause, sleep=time.sleep,
                 monotonic=time.perf_counter):
    state = sim.reset(seed, difficulty)
    det = WavedashDetector(state, sim.ours, sim.forward, max_ticks=max_ticks)
    print(f'\n--- {label} ---', flush=True)
    print('Scenario car:', 'ORANGE' if state.cars[sim.ours].is_orange else 'BLUE',
          f'| seed={seed} | controller={params if params is not None else "idle"}', flush=True)
    print('Tip: In RLViser press Esc to hide menu, then 1 or 2 for a CAR camera (not 9 / ball camera).', flush=True)
    delay = 1.0 / (120. * speed)
    last_dodge = False
    last_grounded = bool(state.cars[sim.ours].on_ground)
    try:
        for t in range(max_ticks):
            started = monotonic()
            if (t % frame_skip == 0):
                renderer.render(state, {})
            action = (ZERO.copy() if params is None else macro_control(params, t, variant=variant))
            state = sim.step(action)
            m = det.observe(state, action)
            row = build_row(label, trial, t + 1, state, sim, det, action)
            writer.writerow(row)
            grounded = bool(state.cars[sim.ours].on_ground)
            if m.dodge_detected and not last_dodge:
                print(f'  t={(t + 1) / 120:.3f}s: DODGE starts, z={row["z"]:.1f}, '
                      f'forward_speed={row["forward_speed"]:.0f}', flush=True)
            if grounded and not last_grounded:
                print(f'  t={(t + 1) / 120:.3f}s: LANDING, '
                      f'dodge_contact={m.landed_during_dodge}, gain={m.speed_gain:+.0f}', flush=True)
            last_dodge = m.dodge_detected
            last_grounded = grounded
            if det.done:
                renderer.render(state, {})
                break
            remaining = delay - (monotonic() - started)
            if remaining > 0: sleep(remaining)
        m = det.metrics
        print(f'RESULT: success={m.success} | reason={m.reason} | '
              f'dodge={m.dodge_detected} | near_ground={m.dodge_near_ground} | '
              f'landed_during_dodge={m.landed_during_dodge} | '
              f'wheels_down={m.wheels_down} | gain={m.speed_gain:+.0f} uu/s | '
              f'rotation={m.total_rotation_deg:.1f} deg', flush=True)
        if pause > 0:
            sleep(pause)
        return m
    except KeyboardInterrupt:
        print('\nViewer stopped.', flush=True)
        raise


def watch(args, *, simulator_factory=Simulator, renderer_factory=None):
    if not (0.1 <= args.speed <= 4): raise ValueError('--speed must be between 0.1 and 4')
    if args.frame_skip < 1 or args.max_ticks < 1 or args.repeat < 1:
        raise ValueError('--frame-skip, --max-ticks and --repeat must be positive')
    selected = attempts(args.mode, args.data, args.seed, args.generation)
    out = args.trace or (args.data / 'viewer_traces' / f'{args.mode}_trace.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    if renderer_factory is None:
        try:
            from rlgym.rocket_league.rlviser import RLViserRenderer
        except ImportError as e:
            raise RuntimeError('RLViser not installed. Use the same environment as WATCH_NATIVE_TUNED_SELFPLAY.bat') from e
        renderer_factory = RLViserRenderer
    sim = simulator_factory()
    renderer = None
    try:
        renderer = renderer_factory(tick_rate=120 * args.speed / args.frame_skip)
        print('REPLAY ONLY. No training, no actor weights changed.', flush=True)
        print('Red flags: big flips, no landing near dodge, or speed gain without clean contact.', flush=True)
        print(f'Mode={args.mode} | speed={args.speed}x | render every {args.frame_skip} physics ticks', flush=True)
        with out.open('w', newline='', encoding='utf-8') as fp:
            writer = csv.DictWriter(fp, fieldnames=FIELDS)
            writer.writeheader()
            trial = 0
            for cycle in range(args.repeat):
                for label, params, variant, difficulty, seed in selected:
                    trial += 1
                    render_trial(sim, renderer, label=label, params=params, variant=variant,
                                 difficulty=difficulty, seed=seed, trial=trial,
                                 writer=writer, max_ticks=args.max_ticks, speed=args.speed,
                                 frame_skip=args.frame_skip, pause=args.pause)
                    fp.flush()
        print('\nTrace saved:', out.resolve(), flush=True)
    except KeyboardInterrupt:
        print('\nStopped by user; partial CSV should be available.', flush=True)
    finally:
        if renderer is not None:
            renderer.close()
        sim.close()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Watch saved SkillForge wavedash attempts in RLViser, no training')
    p.add_argument('--data', type=Path, default=DEFAULT_FOLDER,
                   help='Folder containing discovery.json from your completed search')
    p.add_argument('--mode', choices=('best', 'progress', 'generation', 'dodge', 'idle'), default='best')
    p.add_argument('--generation', type=int, default=None)
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--speed', type=float, default=0.5, help='Sim seconds per wall clock second')
    p.add_argument('--frame-skip', type=int, default=2, help='Render every N physics ticks (sim remains 120Hz)')
    p.add_argument('--max-ticks', type=int, default=100)
    p.add_argument('--repeat', type=int, default=5)
    p.add_argument('--pause', type=float, default=1.3, help='Pause between attempts')
    p.add_argument('--trace', type=Path, default=None)
    return p.parse_args(argv)


if __name__ == '__main__':
    try:
        watch(parse_args())
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print('\nERROR:', e, flush=True)
        raise SystemExit(1)
