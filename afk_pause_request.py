"""Safely request an AFK training pause at the next saved PPO rollout.

Does not signal, kill, or modify any training model. Only creates the pause file
in the most recent active AFK run (or in an explicit valid run folder).
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'data' / 'afk_runs'


def target_run(explicit: Path | None):
    run_base = RUNS.resolve()
    choices = [explicit] if explicit else sorted((p for p in RUNS.iterdir() if p.is_dir()), reverse=True) if RUNS.exists() else []
    for candidate in choices:
        candidate = Path(candidate).resolve()
        if candidate.parent != run_base:
            raise ValueError('Only runs directly under data/afk_runs may be paused')
        status_file = candidate / 'STATUS.json'
        if not status_file.is_file():
            continue
        status = json.loads(status_file.read_text(encoding='utf-8'))
        if status.get('stage') in ('precheck','training'):
            return candidate,status
        if explicit is not None:
            raise RuntimeError('Run is not active (stage: ' + str(status.get('stage')) + ')')
    raise RuntimeError('No training/precheck AFK job found. If evaluating postcheck, let it finish; if paused, use RESUME.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,help='Optional explicit data/afk_runs/TIMESTAMP run directory')
    args = parser.parse_args()
    run,status = target_run(args.run)
    marker = run/'PAUSE_REQUESTED'
    with marker.open('x',encoding='utf8') if not marker.exists() else marker.open('w',encoding='utf8') as out:
        out.write('pause requested '+ datetime.now(timezone.utc).isoformat() +' by pid '+str(os.getpid())+'\n')
    print('PAUSE REQUESTED FOR:',run)
    print('This does NOT stop immediately. Wait for the next saved rollout/stage boundary.')
    print('Leave the training window open until it says PAUSED and STATUS.json stage=paused.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
