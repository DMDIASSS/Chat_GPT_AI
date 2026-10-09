"""Watch a 1-car wavedash attempt. Ball sits directly ahead; never trains model."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time

import numpy as np

from sf2_core import SoloSimulator, Script, HeightTriggeredDodge, Detector, ZERO

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'data' / 'skillforge_v2' / 'calibration.json'
FIELDNAMES = ('attempt','tick','seconds','car_y','ball_y','center_z','on_ground',
              'wheels_in_contact','up_z','forward_speed','vertical_speed','rotation_deg',
              'jump','pitch','has_flipped','is_flipping','dodge_detected',
              'landing_during_dodge','success','failure_reason')


def load_script(mode: str, saved: Path):
    if mode == 'best':
        if not saved.exists():
            raise FileNotFoundError(f'No search file: {saved}\nRun SF2_2_SEARCH_TIMING.bat first.')
        data = json.loads(saved.read_text(encoding='utf-8'))
        return Script(**data['candidate'])
    if mode == 'timed':
        return Script(threshold=38., nose=0.22, cancel_ticks=14)
    if mode == 'late':
        return Script(threshold=29., nose=0.22, cancel_ticks=14)
    if mode == 'early':
        return Script(threshold=80., nose=0.16, cancel_ticks=16)
    if mode == 'idle':
        return Script(threshold=0.)
    raise ValueError(mode)


def trace_row(i, tick, state, car_id, action, metrics):
    c = state.cars[car_id]
    return dict(attempt=i, tick=tick, seconds=round(tick/120., 4),
                car_y=round(float(c.physics.position[1]), 1),
                ball_y=round(float(state.ball.position[1]), 1),
                center_z=round(float(c.physics.position[2]), 2),
                on_ground=int(bool(c.on_ground)),
                wheels_in_contact=sum(bool(x) for x in c.wheels_with_contact),
                up_z=round(float(c.physics.rotation_mtx[2,2]), 3),
                forward_speed=round(float(c.physics.linear_velocity[1]), 1),
                vertical_speed=round(float(c.physics.linear_velocity[2]), 1),
                rotation_deg=round(metrics.rotation_before_landing_deg, 1),
                jump=int(action[5]>0),pitch=float(action[2]),
                has_flipped=int(c.has_flipped), is_flipping=int(c.is_flipping),
                dodge_detected=int(metrics.dodge),
                landing_during_dodge=int(metrics.landing_during_dodge),
                success=int(metrics.success),failure_reason=metrics.reason)


def run(args, simulator_factory=SoloSimulator, renderer_factory=None,
        sleep=time.sleep, perf=time.perf_counter):
    if args.speed <= 0 or args.repeat <= 0 or args.frame_skip <= 0 or args.max_ticks <= 0:
        raise ValueError('invalid viewer parameters')
    script = load_script(args.mode, args.file)
    if renderer_factory is None:
        from rlgym.rocket_league.rlviser import RLViserRenderer
        renderer_factory = RLViserRenderer
    sim = simulator_factory()
    renderer = None
    try:
        renderer = renderer_factory(tick_rate=120 * args.speed / args.frame_skip)
        args.trace.parent.mkdir(parents=True, exist_ok=True)
        print('SOLO wavedash calibration — no model training, exactly 1 car.', flush=True)
        print('Ball is FORWARD of blue car, visual waypoint only; goal is forward (+Y).', flush=True)
        print(f'Mode={args.mode} script={script} replay={args.repeat} speed={args.speed}', flush=True)
        print('Camera: press Esc to close menu, then 1 to follow the blue car.', flush=True)
        with args.trace.open('w', newline='', encoding='utf8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for i in range(args.repeat):
                seed = args.seed + (i % args.seeds)
                state = sim.reset(seed, script.nose)
                assert len(state.cars) == 1
                ctrl = HeightTriggeredDodge(script)
                detector = Detector(state, sim.ours, max_ticks=args.max_ticks)
                print(f'\nAttempt {i+1}/{args.repeat} seed={seed}: car={state.cars[sim.ours].physics.position.round(1)} '
                      f'ball={state.ball.position.round(1)}', flush=True)
                # Freeze each new spawn for camera/readability; engine does not move during this pause.
                renderer.render(state, {})
                sleep(args.spawn_pause)
                previous_ground = bool(state.cars[sim.ours].on_ground)
                prev_dodge = False
                for tick in range(args.max_ticks):
                    clock = perf()
                    action = ctrl.action(state.cars[sim.ours])
                    state = sim.step(action)
                    m = detector.observe(state, action)
                    writer.writerow(trace_row(i+1, tick+1, state, sim.ours, action, m))
                    c = state.cars[sim.ours]
                    if m.dodge and not prev_dodge:
                        print(f'  DODGE at t={(tick+1)/120:.3f}s, z={c.physics.position[2]:.1f}, '
                              f'impulse={m.impulse_gain:+.0f}, pitch={action[2]:g}', flush=True)
                    if c.on_ground and not previous_ground:
                        print(f'  LAND at t={(tick+1)/120:.3f}s, z={c.physics.position[2]:.1f}, '
                              f'contact_wheels={sum(bool(x) for x in c.wheels_with_contact)}, '
                              f'during_dodge={m.landing_during_dodge}', flush=True)
                    prev_dodge = m.dodge
                    previous_ground = bool(c.on_ground)
                    if tick % args.frame_skip == 0 or detector.done:
                        renderer.render(state, {})
                    if detector.done:
                        break
                    wait = 1./(120 * args.speed) - (perf()-clock)
                    if wait>0: sleep(wait)
                m=detector.metrics
                print(f'RESULT={"PASS" if m.success else "FAIL"} {m.reason} '
                      f'| landed_during_dodge={m.landing_during_dodge} '
                      f'| gain={m.final_speed-m.initial_speed:+.0f} '
                      f'| rotation={m.rotation_before_landing_deg:.0f}° '
                      f'| lowest_center_z={m.lowest_center_z:.1f}',flush=True)
                f.flush()
                sleep(args.pause)
        print('Trace:', args.trace.resolve(), flush=True)
    finally:
        if renderer is not None:
            renderer.close()
        sim.close()


def parse(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--mode', choices=['timed','late','early','best','idle'], default='timed')
    p.add_argument('--file', type=Path, default=DEFAULT)
    p.add_argument('--speed', type=float, default=0.55)
    p.add_argument('--seed', type=int, default=700)
    p.add_argument('--seeds', type=int, default=3)
    p.add_argument('--repeat', type=int, default=6)
    p.add_argument('--max-ticks', type=int, default=115)
    p.add_argument('--frame-skip', type=int, default=1)
    p.add_argument('--spawn-pause', type=float, default=0.7)
    p.add_argument('--pause', type=float, default=1.)
    p.add_argument('--trace', type=Path, default=ROOT/'data'/'skillforge_v2'/'viewer_trace.csv')
    return p.parse_args(argv)


if __name__ == '__main__':
    try:
        run(parse())
    except (OSError, RuntimeError, ValueError, AssertionError) as e:
        print('ERROR:',e,flush=True)
        raise SystemExit(1)
