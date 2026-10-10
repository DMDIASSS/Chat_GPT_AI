"""A self-contained browser camera for RocketSim: does not change models or RLViser.
Only serves to 127.0.0.1; requires the original project, PyTorch and RocketSim.
"""
from __future__ import annotations
import argparse
import json
import random
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SCENE = ROOT / 'rl_camera_view.html'


def serialize(state, score=None):
    """Capture physics by value before passing the snapshot to an HTTP handler."""
    ball = state.ball
    cars = []
    for _, car in sorted(state.cars.items(), key=lambda kv: bool(kv[1].is_orange)):
        phys = car.physics
        mat = np.asarray(phys.rotation_mtx, dtype=float).reshape(3, 3)
        cars.append({
            'team': 'orange' if car.is_orange else 'blue',
            'pos': np.asarray(phys.position, dtype=float).tolist(),
            'vel': np.asarray(phys.linear_velocity, dtype=float).tolist(),
            'forward': mat[:, 0].tolist(),
            'right': mat[:, 1].tolist(),
            'up': mat[:, 2].tolist(),
            'boost': round(float(car.boost_amount), 1),
            'ground': bool(getattr(car, 'on_ground', False)),
        })
    return {
        'ball': {'pos': np.asarray(ball.position, dtype=float).tolist(),
                 'vel': np.asarray(ball.linear_velocity, dtype=float).tolist()},
        'cars': cars,
        'pads': (np.asarray(state.boost_pad_timers, dtype=float) <= 0.00001).tolist(),
        'score': dict(score or {'blue': 0, 'orange': 0}),
        'timestamp': time.monotonic(),
    }


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = None
        self.error = None
        self.stop = threading.Event()

    def put(self, data):
        with self.lock:
            self.value = data

    def get(self):
        with self.lock:
            return self.value


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlsplit
            path = urlsplit(self.path).path
            if path == '/':
                content = SCENE.read_bytes()
                kind = 'text/html; charset=utf-8'
            elif path == '/state':
                content = json.dumps({'frame': store.get(), 'error': store.error}).encode('utf-8')
                kind = 'application/json'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass
    return Handler


def simulate(store, path, opponent, speed, seed):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    from watch_latest_ai import NativeController, ModelChoice

    rng = np.random.default_rng(seed)
    blue = NativeController(ModelChoice('native', path))
    orange = None if opponent == 'self' else NativeController(
        ModelChoice('native' if opponent == 'champion' else 'nexto',
                    ROOT/'data'/'autoleague'/'champion.pt' if opponent == 'champion'
                    else ROOT/'vendor'/'nexto'/'nexto-model.pt'))
    engine = RocketSimEngine(rlbot_delay=False)
    score = {'blue': 0, 'orange': 0}
    try:
        while not store.stop.is_set():
            base = engine.create_base_state()
            FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(base,{})
            KickoffMutator().apply(base,{})
            state = engine.set_state(base,{})
            previous = {}
            for t in range(900):
                if store.stop.is_set():
                    return
                start = time.monotonic()
                store.put(serialize(state, score))
                if orange is None:
                    commands = blue.actions(state, previous, 'greedy', rng)
                else:
                    bcmd = blue.actions(state, previous, 'greedy', rng)
                    ocmd = orange.actions(state, previous, 'greedy', rng)
                    commands = {a: (bcmd[a] if not c.is_orange else ocmd[a]) for a,c in state.cars.items()}
                state = engine.step({car: np.tile(action, (8,1)) for car,action in commands.items()}, {})
                previous = commands
                if getattr(state, 'goal_scored', False):
                    who = 'blue' if float(state.ball.position[1]) > 0 else 'orange'
                    score[who] += 1
                    store.put(serialize(state,score))
                    if store.stop.wait(1.2): return
                    break
                remaining = (1 / (15 * speed)) - (time.monotonic() - start)
                if remaining > 0:
                    store.stop.wait(remaining)
    except Exception as e:
        store.error = f'{type(e).__name__}: {e}'
        raise
    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', default='data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt')
    parser.add_argument('--opponent', choices=['self','nexto','champion'], default='nexto')
    parser.add_argument('--speed', type=float, default=1.0)
    parser.add_argument('--seed',type=int, default=2409)
    parser.add_argument('--port', type=int, default=8765)
    display=parser.add_mutually_exclusive_group()
    display.add_argument('--window',action='store_true',help='Launch native Windows WebView2 desktop window')
    display.add_argument('--browser',action='store_true',help='Explicitly launch a browser tab instead')
    args = parser.parse_args()
    if not 0.1 <= args.speed <= 10.0 or not 1024 <= args.port <= 65535:
        parser.error('speed range 0.1..10; port 1024..65535')
    checkpoint = (ROOT / args.checkpoint).resolve()
    if not checkpoint.is_file():
        parser.error('Model not found: ' + str(checkpoint))
    store = Store()
    server = ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(store))
    server.daemon_threads=True
    thread = threading.Thread(target=simulate,args=(store,checkpoint,args.opponent,args.speed,args.seed),daemon=True)
    thread.start()
    print(f'Camera viewer: http://127.0.0.1:{args.port}/',flush=True)
    print(f'Model: {checkpoint}; opponent: {args.opponent}; Ctrl+C to stop.',flush=True)
    url=f'http://127.0.0.1:{args.port}/'
    try:
        if args.window:
            # Fully separate app window; pywebview on Windows uses Edge WebView2.
            try:import webview
            except ImportError as exc:
                raise RuntimeError('Windowed viewer requires pywebview. Run: .venv\\Scripts\\python.exe -m pip install pywebview') from exc
            server_thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.25},daemon=True)
            server_thread.start()
            webview.create_window('AFK Improved — RocketSim Camera',url,width=1440,height=810,
                                  min_size=(860,540),background_color='#171d25')
            webview.start(debug=False)
        else:
            if args.browser:webbrowser.open(url)
            server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:pass
    finally:
        store.stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__=='__main__':
    main()
