"""Read game-resolved local human controls from BakkesMod Input Bridge (120 Hz).

Only connects to 127.0.0.1. No global keyboard hooks. Original data is kept in
JSONL without destructive modifications. Does NOT collect ball/opponent states.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time

WS_URL = 'ws://127.0.0.1:49200'


def safe_output(out: str) -> Path:
    path = Path(out).resolve()
    if path.suffix.lower() != '.jsonl':
        raise ValueError('Output file must end in .jsonl')
    if path.exists():
        raise FileExistsError(f'Refusing to overwrite: {path}')
    return path


def make_record(packet: dict, monotonic_ns: int, utc: str) -> dict:
    if not isinstance(packet, dict) or packet.get('t') not in ('input', 'settings'):
        raise ValueError('Expected an Input Bridge input/settings message')
    return {'recv_monotonic_ns': monotonic_ns, 'recv_utc': utc, 'data': packet}


def parse_capture(path: Path) -> dict:
    count, settings_count, bad, first, last = 0, 0, 0, None, None
    on_ground, boosting, jump, dodge_starts = 0, 0, 0, 0
    speeds = []
    prev_dodge_active = False
    for line in path.open('r', encoding='utf-8'):
        try:
            row = json.loads(line)
            packet = row['data']
            if packet.get('t') == 'settings':
                settings_count += 1
                continue
            if packet.get('t') != 'input':
                continue
            stamp = int(row['recv_monotonic_ns'])
            first = stamp if first is None else first
            last = stamp
            count += 1
            on_ground += bool(packet.get('onGround', 0))
            boosting += bool(packet.get('holdBoost', 0))
            jump += bool(packet.get('jump', 0))
            dodge_active = float(packet.get('dodgeT', 0) or 0) > 0
            dodge_starts += dodge_active and not prev_dodge_active
            prev_dodge_active = dodge_active
            vel = packet.get('vel')
            if isinstance(vel, list) and len(vel) == 3:
                speeds.append(sum(float(v)*float(v) for v in vel) ** 0.5)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            bad += 1
    duration = max(0, (last - first) / 1e9) if count >= 2 else 0.0
    return {'input_frames': count, 'settings_messages': settings_count,
            'corrupt_records': bad, 'observed_seconds': round(duration, 3),
            'observed_rate_hz': round((count-1)/duration, 2) if duration else None,
            'ground_fraction': round(on_ground/count, 4) if count else None,
            'boost_held_fraction': round(boosting/count, 4) if count else None,
            'jump_held_fraction': round(jump/count, 4) if count else None,
            'dodge_starts_detected': int(dodge_starts),
            'mean_speed_uu_s': round(statistics.mean(speeds), 2) if speeds else None,
            'note': 'Local input/vehicle-only capture; NOT yet paired with ball, opponent and boost-pad observations.'}


async def record(out: Path, seconds: float, port: int) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit('Install websocket dependency: .venv\\Scripts\\python.exe -m pip install websockets') from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    url = f'ws://127.0.0.1:{port}'
    end_ns = time.monotonic_ns() + int(seconds * 1e9)
    input_count = 0
    print('CONNECTING_LOCAL_INPUT_BRIDGE', url, flush=True)
    try:
        async with websockets.connect(url, max_size=2**20, open_timeout=8, ping_interval=20) as ws:
            with out.open('x', encoding='utf-8', buffering=262144) as f:
                print('RECORDING_GAME_INPUT', out, flush=True)
                while True:
                    remaining = (end_ns-time.monotonic_ns()) / 1e9
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(2.0, remaining))
                    except asyncio.TimeoutError:
                        continue
                    try:
                        packet = json.loads(raw)
                        row = make_record(packet, time.monotonic_ns(), datetime.now(timezone.utc).isoformat())
                    except (ValueError, TypeError):
                        continue
                    f.write(json.dumps(row, separators=(',', ':'), ensure_ascii=False) + '\n')
                    if packet['t'] == 'input':
                        input_count += 1
                    if input_count and input_count % 1200 == 0:
                        f.flush()
                        print('RECORDED_FRAMES', input_count, flush=True)
    except (OSError, ConnectionError) as exc:
        print('CONNECTION_ERROR', type(exc).__name__, str(exc), flush=True)
        print('If connection was refused, check BakkesMod Input Bridge is installed and active.', flush=True)
        raise SystemExit(2) from exc
    print('RECORDING_COMPLETE', json.dumps({'path': str(out), **parse_capture(out)}), flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    rp = sub.add_parser('record', help='Save human game-resolved inputs for specified seconds')
    rp.add_argument('--out', required=True)
    rp.add_argument('--seconds', type=float, default=60.0)
    rp.add_argument('--port', type=int, default=49200)
    ap = sub.add_parser('analyze', help='Summarize a recorded JSONL file')
    ap.add_argument('--input', required=True)
    a = p.parse_args()
    if a.cmd == 'record':
        if not (1 <= a.seconds <= 1800):
            p.error('--seconds must be 1..1800')
        if not (1024 <= a.port <= 65535):
            p.error('--port must be 1024..65535')
        asyncio.run(record(safe_output(a.out), a.seconds, a.port))
    else:
        print('HUMAN_INPUT_AUDIT', json.dumps(parse_capture(Path(a.input).resolve()), sort_keys=True))


if __name__ == '__main__':
    main()
