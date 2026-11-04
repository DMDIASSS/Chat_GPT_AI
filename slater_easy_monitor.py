"""Optional read-only campaign telemetry: local JSONL is canonical; W&B is a mirror.

No torch import, no changes to training state or checkpoints, no online login prompt.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent
CAMPAIGNS = ROOT / 'data' / 'isolated' / 'champion_campaigns'
MONITORS = ROOT / 'data' / 'isolated' / 'easy_monitor'


def safe_name(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', value):
        raise ValueError('Campaign ID must be 1-40 ASCII letters/numbers/_/-')
    return value


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError, OSError):
        return default


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix(path.suffix + '.tmp')
    target.write_text(json.dumps(value, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(target, path)


def metrics_for(run_name: str, campaign_dir: Path | None = None) -> tuple[dict, dict]:
    """Expose measured counters only. No reward/loss fields are invented."""
    run_name = safe_name(run_name)
    folder = campaign_dir or CAMPAIGNS / run_name
    progress = read_json(folder / 'progress.json', {}) or {}
    selected = read_json(folder / 'selected.json', {}) or {}
    if not progress:
        return {}, {}
    values = {}
    for key in ('cycle', 'train_updates', 'evaluation_games', 'promotions', 'elapsed_seconds',
                'branch_updates', 'completed_games', 'total_games'):
        v = progress.get(key)
        if isinstance(v, (float, int)) and not isinstance(v, bool):
            values['campaign/' + key] = v
    values['campaign/phase'] = str(progress.get('phase') or '')
    values['campaign/status'] = str(progress.get('status') or '')
    values['campaign/routine'] = str(progress.get('routine') or '')
    values['champion/model_id'] = str(selected.get('model_id') or progress.get('champion_id') or '')
    values['champion/verified_simulator_promotions'] = progress.get('promotions', 0)
    # A decision is not a certified human/SSL win; log the actual reason.
    branches = progress.get('branches') or []
    if branches:
        last = branches[-1]
        if isinstance(last, dict):
            values['campaign/last_branch_result'] = str(last.get('result') or '')
            values['campaign/last_branch_routine'] = str(last.get('routine') or '')
    current = progress.get('active')
    if isinstance(current, dict):
        values['campaign/active_branch'] = str(current.get('run_name') or '')
        values['campaign/active_updates'] = int(current.get('updates') or 0)
    # For eval results, only report numbers already established by saved reports.
    evidence = {}
    cycle = progress.get('cycle')
    if isinstance(cycle, int) and cycle >= 1:
        stage = folder / 'branches' / f'cycle_{cycle:06d}'
        for fname, tag in (('screen.json', 'screen'), ('confirmation.json', 'confirmation')):
            report = read_json(stage / fname, {}) or {}
            if report.get('complete') is True:
                evidence[tag] = {'games': report.get('completed_games'), 'seeds': len(report.get('seeds', []))}
                values[f'evaluation/{tag}_games'] = report.get('completed_games', 0)
    # Actual native C++ update files are written atomically after each PPO update.
    # This works while the campaign controller is still blocked collecting a chunk.
    native_details = None
    active = progress.get('active') or {}
    branch_name = active.get('run_name') if isinstance(active, dict) else None
    if isinstance(branch_name, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', branch_name):
        native_dir = folder.parents[1] / 'native_attention' / 'runs' / branch_name
        native_progress = read_json(native_dir / 'progress.json', {}) or {}
        update_num = native_progress.get('updates')
        if isinstance(update_num, int) and update_num >= 1:
            native_details = read_json(native_dir / f'update_{update_num}.json', {}) or {}
            for key in ('actor_loss', 'value_loss', 'teacher_kl', 'entropy',
                        'clip_fraction', 'rollout_policy_kl', 'target_kl',
                        'accepted_actor_epochs', 'backtracks', 'rejected_policy_kl',
                        'collection_decisions_per_second', 'overall_decisions_per_second',
                        'collection_seconds', 'optimization_seconds', 'checkpoint_seconds'):
                value = native_details.get(key)
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    values['native/' + key] = value
            values['native/updates'] = update_num
            if isinstance(native_progress.get('decisions'), int):
                values['native/decisions'] = native_progress['decisions']
    # Keep stable event identity based on persisted campaign and native update state.
    identity = {
        'cycle': progress.get('cycle'), 'phase': progress.get('phase'),
        'status': progress.get('status'), 'updates': progress.get('train_updates'),
        'eval_games': progress.get('evaluation_games'), 'promotions': progress.get('promotions'),
        'champion': selected.get('model_id'), 'evidence': evidence,
        'native_update': native_details.get('update') if native_details else None,
    }
    return values, identity


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class Mirror:
    def __init__(self, name: str, store: Path, sdk=None, *, mode: str = 'auto'):
        self.name = safe_name(name)
        self.store = store
        self.store.mkdir(parents=True, exist_ok=True)
        self.state_path = store / 'bridge_state.json'
        self.events_path = store / 'events.jsonl'
        self.state = read_json(self.state_path, {}) or {}
        self.sdk = sdk
        self.mode = mode
        self.run = None
        self.state.setdefault('sequence', 0)
        self.state.setdefault('last_fingerprint', '')
        self.state.setdefault('mode', 'local')

    def poll(self, campaign_dir: Path | None = None):
        metrics, identity = metrics_for(self.name, campaign_dir)
        if not metrics:
            return False
        sig = fingerprint(identity)
        if sig == self.state['last_fingerprint']:
            return False
        seq = int(self.state['sequence']) + 1
        event = {'sequence': seq, 'timestamp': time.time(), 'campaign': self.name,
                 'metrics': metrics, 'identity_sha256': sig}
        # Always persist local progress; W&B upload is best effort.
        with self.events_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(event, sort_keys=True) + '\n')
        self.state.update(sequence=seq, last_fingerprint=sig,
                          last_local_event=time.time())
        atomic_json(self.state_path, self.state)
        if self.run is not None:
            try:
                self.run.log(metrics, step=seq)
                self.state['last_sync'] = time.time()
                self.state.pop('last_sync_error', None)
            except Exception as exc:
                # W&B must never affect the training decision or model.
                self.state['last_sync_error'] = type(exc).__name__
            atomic_json(self.state_path, self.state)
        return True

    def connect(self):
        if self.mode == 'local':
            return False
        # A logged-in W&B SDK may read ~/.netrc; never read, print or store its token ourselves.
        has_auth = bool(os.getenv('WANDB_API_KEY'))
        netrc_paths = [Path.home() / '.netrc', Path.home() / '_netrc']
        if not has_auth and any(path.is_file() for path in netrc_paths):
            # The SDK will decide whether valid W&B credentials exist there.
            has_auth = True
        if not has_auth and self.mode == 'auto':
            self.state['mode'] = 'local'
            atomic_json(self.state_path, self.state)
            return False
        sdk = self.sdk
        if sdk is None:
            try:
                import wandb as sdk
            except ImportError:
                self.state['mode'] = 'local_no_sdk'
                atomic_json(self.state_path, self.state)
                return False
        try:
            chosen_mode = 'offline' if self.mode == 'offline' else 'online'
            os.environ['WANDB_SILENT'] = 'true'
            os.environ['WANDB_CONSOLE'] = 'off'
            # resume allows reattaching to a previous public run after a safe restart.
            run = sdk.init(project='slater-ai', group=self.name,
                           id='slater-' + hashlib.sha256(self.name.encode()).hexdigest()[:16],
                           resume='allow', mode=chosen_mode,
                           name=f'{self.name}-campaign',
                           config={'campaign': self.name, 'purpose': 'telemetry_only'},
                           settings=sdk.Settings(init_timeout=20))
            if run is None:
                raise RuntimeError('W&B did not return a run')
            self.run = run
            self.state['mode'] = chosen_mode
            if getattr(run, 'url', None):
                self.state['url'] = str(run.url)
            atomic_json(self.state_path, self.state)
            if self.state.get('url'):
                print('W&B dashboard:', self.state['url'], flush=True)
            return True
        except Exception as exc:
            self.state.update(mode='local_wandb_unavailable', last_sync_error=type(exc).__name__)
            atomic_json(self.state_path, self.state)
            return False

    def close(self):
        if self.run is not None:
            try:
                self.run.finish()
            except Exception:
                pass


@contextmanager
def single_monitor(store: Path):
    """Process-scoped lock; safe after process crash, unlike stale PID files."""
    store.mkdir(parents=True, exist_ok=True)
    with (store / 'monitor.lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Monitor already running for this campaign') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('Monitor already running for this campaign') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    p = argparse.ArgumentParser(description='Read-only Slater campaign W&B/local progress bridge')
    p.add_argument('command', choices=['once', 'follow', 'status'])
    p.add_argument('--run', default='slater_easy01', type=safe_name)
    p.add_argument('--mode', choices=['auto', 'local', 'offline', 'online'], default='auto')
    p.add_argument('--interval', type=int, default=10)
    a = p.parse_args(argv)
    store = MONITORS / a.run
    monitor = Mirror(a.run, store, mode=a.mode)
    if a.command == 'status':
        print(json.dumps(read_json(monitor.state_path, {'status': 'not_started'}), indent=2))
        return 0
    if a.command == 'once':
        monitor.poll()
        print(json.dumps(monitor.state, indent=2))
        return 0
    # At most one monitor owns a campaign's W&B run at a time.
    with single_monitor(store):
        monitor.connect()
        try:
            while True:
                monitor.poll()
                time.sleep(max(2, a.interval))
        except KeyboardInterrupt:
            return 0
        finally:
            monitor.close()


if __name__ == '__main__':
    sys.exit(main())
