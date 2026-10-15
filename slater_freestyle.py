"""Independent from-scratch Freestyle runs, local desktop controls and W&B telemetry.

The original playing models never enter this trainer. Credentials belong to W&B's
local login/environment, never to a run's immutable JSON or the native child.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from slater_v041_core import atomic_json, read_json, sha256, process_lock

ROOT = Path(__file__).resolve().parent
HERE = ROOT / 'GigaLearn_Project/Freestyle'
BASE = ROOT / 'data/isolated/freestyle'
SCHEMA = 'slater-freestyle-v1'
RUN_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SECRET_KEY = re.compile(r'(?:^|_)(?:token|password|secret|api_key|authorization)(?:$|_)', re.I)
REDACT_ENV = ('WANDB_API_KEY', 'WANDB_ACCESS_TOKEN', 'WANDB_IDENTITY_TOKEN_FILE')
STAGES = ('contact_pop', 'air_carry', 'reset_acquire', 'reset_use', 'multi_reset',
          'pinch_proxy', 'double_tap_proxy', 'psycho_proxy', 'wall_recovery', 'walldash_proxy')


def reward_defaults():
    return {'weights': {'approach': .15, 'jump_explore': .025, 'ball_touch': .6,
        'wall_roll': .7, 'wall_pop': 1.1, 'air_touch': 1.3, 'nose_control': .8,
        'air_carry': 2., 'reset_acquire': 3., 'reset_use': 4., 'multi_reset': 5.,
        'pinch_proxy': 3., 'double_tap_proxy': 4., 'psycho_proxy': 5.,
        'wall_recovery': 1.5, 'walldash_proxy': 2.5, 'shot_progress': .5,
        'goal': 2., 'qualified_finish': 6., 'concede': .15, 'idle': .02,
        'lift_progress': 1.5, 'pop_retouch': 2.},
        'max_episode_positive': 36., 'touch_spacing': .12, 'carry_touch_deadline': .35,
        'reset_use_deadline': 2.5, 'flip_touch_deadline': .55, 'finish_deadline': 5.}


def defaults():
    return {
        'schema': SCHEMA, 'run_name': 'freestyle01',
        'native': {
            'games': 16, 'tick_skip': 4, 'action_delay': 1, 'threads': 2, 'sim_threads': 4,
            'device': 'auto', 'seed': 20261014, 'width': 768, 'depth': 3,
            'steps_per_update': 32768, 'minibatch': 2048, 'epochs': 2,
            'actor_lr': .0002, 'critic_lr': .00025, 'gamma': .9975,
            'lambda': .95, 'entropy': .018, 'clip': .2, 'max_updates': 0,
            'save_every_updates': 10, 'stage': 'contact_pop', 'difficulty': 0.,
            'curriculum_enabled': True, 'eval_every_updates': 10,
            'eval_episodes': 16, 'mastery_success_rate': .7, 'mastery_passes': 3,
            'min_stage_updates': 20, 'difficulty_step': .1, 'max_episode_seconds': 12.,
            'target_kl': .02, 'adaptive_lr': True, 'min_actor_lr': .00002,
            'critic_warmup_updates': 0,
            'half_precision': False, 'reward_clip': 10., 'eval_seed_base': 910000000,
            'privileged_dropout': .5, 'defender': 'scripted_goalie',
            'defender_after_stage': 'reset_use', 'defender_strength': .7,
            'rewards': reward_defaults(),
        },
        'wandb': {'mode': 'online', 'project': 'slater-freestyle', 'entity': '',
                  'allow_offline_fallback': True},
    }


def forbid_credentials(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY.search(str(key)):
                raise ValueError('Settings cannot contain credentials; use the local W&B login dialog')
            forbid_credentials(child)
    elif isinstance(value, list):
        for child in value:
            forbid_credentials(child)


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError('Freestyle settings must be a JSON object')
    forbid_credentials(value)
    result = defaults()
    unknown = set(value) - set(result)
    if unknown:
        raise ValueError('Unknown Freestyle setting: ' + ', '.join(sorted(unknown)))
    for key, child in value.items():
        if key in ('native', 'wandb'):
            if not isinstance(child, dict):
                raise ValueError(key + ' must be a JSON object')
            result[key].update(child)
        else:
            result[key] = child
    if result['schema'] != SCHEMA or not RUN_NAME.fullmatch(result['run_name']):
        raise ValueError('Use Freestyle v1 settings and an ASCII run name with 1..64 letters/digits/_/-')
    native = result['native']
    unknown = set(native) - set(defaults()['native'])
    if unknown:
        raise ValueError('Unknown native parameter: ' + ', '.join(sorted(unknown)))
    ranges = {
        'games': (1, 256), 'tick_skip': (1, 8), 'action_delay': (0, 7),
        'threads': (1, 32), 'sim_threads': (1, 32), 'seed': (0, 2147483647), 'width': (64, 2048),
        'depth': (1, 6), 'steps_per_update': (512, 1000000),
        'minibatch': (128, 1000000), 'epochs': (1, 8), 'max_updates': (0, 10000000),
        'save_every_updates': (1, 1000), 'eval_every_updates': (1, 10000),
        'eval_episodes': (2, 256), 'mastery_passes': (1, 20),
        'min_stage_updates': (1, 1000000), 'eval_seed_base': (0, 2147483647),
        'critic_warmup_updates': (0, 1000),
    }
    for key, (lower, upper) in ranges.items():
        if type(native[key]) is not int or not lower <= native[key] <= upper:
            raise ValueError(f'{key} must be an integer from {lower} to {upper}')
    if native['tick_skip'] not in (1, 2, 4, 8):
        raise ValueError('tick_skip must be 1, 2, 4 or 8')
    if native['action_delay'] >= native['tick_skip']:
        raise ValueError('action_delay must be smaller than tick_skip')
    if native['minibatch'] > native['steps_per_update']:
        raise ValueError('minibatch cannot exceed steps_per_update')
    float_ranges = {'actor_lr': (1e-7, .01), 'critic_lr': (1e-7, .01),
                    'gamma': (.9, .99999), 'lambda': (.5, 1.), 'entropy': (0., 1.),
                    'clip': (.01, .5), 'difficulty': (0., 1.),
                    'mastery_success_rate': (.05, 1.), 'difficulty_step': (.01, 1.),
                    'max_episode_seconds': (1., 120.), 'target_kl': (1e-5, 1.),
                    'min_actor_lr': (1e-7, .01), 'reward_clip': (0., 100.)}
    float_ranges.update(privileged_dropout=(0., 1.), defender_strength=(0., 1.))
    for key, (lower, upper) in float_ranges.items():
        if isinstance(native[key], bool) or not isinstance(native[key], (float, int)) or not math.isfinite(native[key]) or not lower <= native[key] <= upper:
            raise ValueError(f'{key} must be a finite number from {lower} to {upper}')
    if native['device'] not in ('auto', 'cpu', 'cuda'):
        raise ValueError('device must be auto, cpu or cuda')
    for key in ('curriculum_enabled', 'adaptive_lr', 'half_precision'):
        if type(native[key]) is not bool:
            raise ValueError(key + ' must be true or false')
    if native['min_actor_lr'] > native['actor_lr']:
        raise ValueError('min_actor_lr cannot exceed actor_lr')
    if native['stage'] not in STAGES:
        raise ValueError('stage must be a curriculum stage name')
    if native['defender_after_stage'] not in STAGES:
        raise ValueError('defender_after_stage must be a curriculum stage name')
    if native['defender'] not in ('none', 'scripted_goalie'):
        raise ValueError('defender must be none or scripted_goalie')
    rewards = native['rewards']
    allowed_rewards = reward_defaults()
    if not isinstance(rewards, dict) or set(rewards) - set(allowed_rewards):
        raise ValueError('Unknown reward setting')
    merged = deepcopy(allowed_rewards)
    for key, value in rewards.items():
        if key == 'weights':
            if not isinstance(value, dict) or set(value) - set(merged['weights']):
                raise ValueError('Unknown freestyle reward component')
            merged['weights'].update(value)
        else:
            merged[key] = value
    for key, value in merged['weights'].items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 30:
            raise ValueError('Reward weights must be finite numbers from 0 to 30: ' + key)
    for key, value in merged.items():
        if key != 'weights' and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
            raise ValueError('Reward timing/cap must be positive and finite: ' + key)
    native['rewards'] = merged
    monitor = result['wandb']
    if set(monitor) - set(defaults()['wandb']):
        raise ValueError('Unknown W&B setting')
    if monitor['mode'] not in ('online', 'offline', 'disabled'):
        raise ValueError('wandb.mode must be online, offline or disabled')
    if not isinstance(monitor['project'], str) or not monitor['project'] or not isinstance(monitor['entity'], str):
        raise ValueError('W&B project and entity must be strings')
    if type(monitor['allow_offline_fallback']) is not bool:
        raise ValueError('allow_offline_fallback must be true or false')
    return result


def run_path(name):
    if not RUN_NAME.fullmatch(name):
        raise ValueError('Invalid run name')
    return BASE / 'runs' / name


def backend_identity():
    files = sorted(path for path in HERE.iterdir() if
                   (path.suffix in ('.h', '.cpp', '.cmake') or path.name == 'CMakeLists.txt') and path.is_file())
    if not files:
        raise FileNotFoundError('Freestyle native sources are missing')
    return {path.name: sha256(path) for path in files}


def binary_path(folder=None):
    return Path(folder or BASE / 'build').resolve() / ('SlaterFreestyleNative.exe' if os.name == 'nt' else 'SlaterFreestyleNative')


def binary_identity(folder=None):
    binary = binary_path(folder)
    if not binary.is_file():
        raise FileNotFoundError('Build Freestyle first: FREESTYLE_BUILD.bat')
    stamp = read_json(binary.parent / 'build_identity.json', {})
    if stamp.get('backend_sha') != backend_identity():
        raise ValueError('Freestyle sources changed since build; stop the run and use FREESTYLE_BUILD.bat')
    result = {'binary_sha256': sha256(binary), 'backend_sha': stamp['backend_sha'],
              'gigalearn_commit': stamp['gigalearn_commit']}
    for library in (binary.parent / 'giga/GigaLearnCPP.dll', binary.parent / 'giga/libGigaLearnCPP.so'):
        if library.is_file():
            shadow = binary.parent / library.name
            if shadow.is_file() and sha256(shadow) != sha256(library):
                raise ValueError('Freestyle DLL is stale; close its processes and rebuild Freestyle')
            result['library_sha256'] = sha256(library)
    return result


def build(folder=None, source=None, jobs=1):
    import torch
    from GigaLearn_Project.Native_Backend import native_setup as helper
    from slater_native_attention import verify_giga_source
    from slater_training_studio import initialize_visual_studio
    if type(jobs) is not int or not 1 <= jobs <= 4:
        raise ValueError('Use 1..4 compiler jobs; 1 is recommended on the 16 GB laptop')
    if source:
        source = verify_giga_source(source)
    else:
        source = BASE / 'source'
        helper.fetch('https://github.com/ZealanL/GigaLearnCPP-Leak.git', source, helper.GIGA)
        helper.patch_source(source)
        source = verify_giga_source(source)
    folder = Path(folder or BASE / 'build').resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cuda_args, environment = helper.cuda_configuration(torch)
    environment = initialize_visual_studio(environment)
    library, include = helper.python_paths()
    configure = [helper.tool('cmake'), '-S', HERE, '-B', folder, '-G', 'Ninja',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_MAKE_PROGRAM=' + helper.tool('ninja'),
                 '-DGIGALEARN_SOURCE=' + source.as_posix(), '-DCMAKE_PREFIX_PATH=' + torch.utils.cmake_prefix_path,
                 '-DPython_EXECUTABLE=' + sys.executable, '-DPYTHON_EXECUTABLE=' + sys.executable,
                 '-DPYTHON_LIBRARY=' + str(library), '-DPYTHON_INCLUDE_DIR=' + str(include), *cuda_args]
    for args in (configure, [helper.tool('cmake'), '--build', folder, '--target', 'SlaterFreestyleNative', '-j', str(jobs)]):
        helper.command(args, env=environment)
    if os.name == 'nt':
        built_library = folder / 'giga/GigaLearnCPP.dll'
        if built_library.is_file():
            temporary = folder / '.Freestyle-GigaLearnCPP.tmp'
            shutil.copyfile(built_library, temporary)
            if sha256(temporary) != sha256(built_library):
                raise RuntimeError('Freestyle DLL changed while copying; rebuild after other compiler jobs stop')
            os.replace(temporary, folder / built_library.name)
    stamp = {'backend_sha': backend_identity(), 'gigalearn_commit': helper.GIGA, 'source': str(source)}
    atomic_json(folder / 'build_identity.json', stamp)
    identity = binary_identity(folder)
    atomic_json(folder / 'build_identity.json', {**stamp, **identity})
    print('FREESTYLE_BUILD_COMPLETE', json.dumps(identity), flush=True)
    return binary_path(folder)


def credential_prompt():
    """Local-only password entry permits normal clipboard paste on Windows."""
    if os.name == 'nt':
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            value = simpledialog.askstring('Weights & Biases local login',
                'Paste your W&B API key here. It is sent only to W&B and saved by its local login.\n'
                'Cancel starts offline when fallback is enabled.', show='*', parent=root)
            root.destroy()
            return (value or '').strip()
        except (ImportError, RuntimeError):
            pass
    if not sys.stdin.isatty():
        return ''
    return getpass.getpass('W&B API key (local input; hidden, Enter to cancel): ').strip()


def configure_login(wandb, mode, *, prompt=True):
    if mode != 'online':
        return True
    from urllib.parse import urlsplit
    configured = bool(os.environ.get('WANDB_API_KEY') or os.environ.get('WANDB_IDENTITY_TOKEN_FILE'))
    if not configured:
        try:
            import netrc
            host = urlsplit(os.environ.get('WANDB_BASE_URL', 'https://api.wandb.ai')).hostname
            configured = bool(netrc.netrc().authenticators(host))
        except (OSError, netrc.NetrcParseError):
            pass
    try:
        if configured:
            return bool(wandb.login(verify=True, timeout=20))
        key = credential_prompt() if prompt else ''
        if not key:
            return False
        try:
            return bool(wandb.login(key=key, verify=True, timeout=20))
        finally:
            key = ''
    except Exception:
        # API exceptions may contain request headers; never send their content to logs.
        print('W&B login failed. Check the local key/account or use offline monitoring.', flush=True)
        return False


def flatten_metrics(event):
    result = {}
    def visit(prefix, value):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(prefix + '/' + str(key) if prefix else str(key), child)
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            result[prefix] = value
        elif isinstance(value, (str, bool)):
            result[prefix] = value
    visit('', event)
    result['train/update'] = int(event.get('update', event.get('updates', event.get('total_updates', 0))))
    result['train/timesteps'] = int(event.get('timesteps', event.get('total_timesteps', 0)))
    # Keep raw diagnostics, but expose the actual learning signals separately
    # from fixed reward coefficients and bookkeeping counters. A coefficient
    # such as weights/wall_pop is not a learned neural-network parameter.
    metrics = event.get('metrics', {})
    if not isinstance(metrics, dict):
        return result
    aliases = {
        'Policy Loss': 'learning/actor_loss',
        'Critic Loss': 'learning/critic_loss',
        'Policy Entropy': 'learning/policy_entropy_normalized',
        'Post-update PPO KL': 'learning/policy_kl_after_update',
        'Policy Update Magnitude': 'learning/actor_parameter_change_l2',
        'Critic Update Magnitude': 'learning/critic_parameter_change_l2',
        'Average Step Reward': 'learning/mean_step_reward',
        'GAE/Avg Return': 'learning/mean_absolute_return',
        'SB3 Clip Fraction': 'learning/clip_fraction',
        'learning_rate/actor': 'learning/actor_lr',
        'learning_rate/critic': 'learning/critic_lr',
        'Overall Steps/Second': 'performance/overall_steps_per_second',
        'Collection Steps/Second': 'performance/collection_steps_per_second',
    }
    for original, name in aliases.items():
        value = metrics.get(original)
        if type(value) in (float, int) and math.isfinite(value):
            result[name] = value
    if type(metrics.get('training/critic_warmup')) is bool:
        result['learning/critic_warmup'] = int(metrics['training/critic_warmup'])
    outcomes = metrics.get('outcomes', {})
    if isinstance(outcomes, dict):
        episodes = sum(value for key, value in outcomes.items() if key.startswith('episodes/')
                       and type(value) in (float, int) and math.isfinite(value))
        successes = sum(value for key, value in outcomes.items() if key.startswith('successes/')
                        and type(value) in (float, int) and math.isfinite(value))
        if episodes > 0:
            result['practice/success_rate'] = successes / episodes
            result['practice/episodes'] = episodes
        for objective in ('touch', 'pop', 'retouch'):
            count = outcomes.get('objectives/' + objective + '/episodes', 0)
            success = outcomes.get('objectives/' + objective + '/successes', 0)
            if type(count) in (float, int) and math.isfinite(count) and count > 0 and \
                    type(success) in (float, int) and math.isfinite(success):
                result['practice/objectives/' + objective + '_success_rate'] = success / count
    components = metrics.get('reward_components', {})
    if isinstance(components, dict):
        for key, value in components.items():
            if key.startswith('weighted_sum/') and type(value) in (float, int) and math.isfinite(value):
                result['reward_contributions/' + key.removeprefix('weighted_sum/')] = value
    evaluation = event.get('evaluation')
    if isinstance(evaluation, dict) and evaluation.get('complete'):
        for key in ('success_rate', 'successes', 'episodes', 'difficulty'):
            value = evaluation.get(key)
            if type(value) in (float, int) and math.isfinite(value):
                result['validation/' + key] = value
        episodes = evaluation.get('episodes', 0)
        telemetry = evaluation.get('telemetry', {})
        if type(episodes) in (float, int) and episodes > 0 and isinstance(telemetry, dict):
            for key, name in (('events/learner_goal', 'goals_per_episode'),
                              ('events/air_touch', 'air_touches_per_episode'),
                              ('events/verified_four_wheel_reset', 'resets_per_episode'),
                              ('events/pop_air_retouch', 'pop_retouches_per_episode'),
                              ('measurements/best_carry_seconds_sum', 'mean_best_carry_seconds')):
                value = telemetry.get(key, 0)
                if type(value) in (float, int) and math.isfinite(value):
                    result['validation/' + name] = value / episodes
            for objective in ('touch', 'pop', 'retouch'):
                count = telemetry.get('objectives/' + objective + '/episodes', 0)
                success = telemetry.get('objectives/' + objective + '/successes', 0)
                if type(count) in (float, int) and math.isfinite(count) and count > 0 and \
                        type(success) in (float, int) and math.isfinite(success):
                    result['validation/objectives/' + objective + '_success_rate'] = success / count
    # Missing evaluations/losses stay missing: they must not become fake zeros.
    return result


class WandbMonitor:
    """Bounded asynchronous telemetry: simulation never waits for metric uploads."""
    def __init__(self, run, settings, protocol, *, prompt=True):
        self.folder, self.settings = Path(run), settings
        self.statefile = self.folder / 'wandb_state.json'
        self.state = read_json(self.statefile, {})
        self.queue = queue.Queue(maxsize=128)
        self.handle = None
        self.thread = None
        self.snapshot_folder = self.folder / 'wandb_uploads' / uuid.uuid4().hex
        self.mode = settings['mode']
        self.failed = False
        previous_mode = self.state.get('mode')
        fallback_step = self.state.get('last_update', -1) if previous_mode == self.mode else -1
        self.last_logged = int(self.state.get('last_' + self.mode + '_update', fallback_step))
        if self.mode == 'disabled':
            return
        try:
            import wandb
        except ImportError:
            if self.mode == 'online' and not settings['allow_offline_fallback']:
                raise RuntimeError('Install GigaLearn_Project/Freestyle/requirements.txt to enable W&B')
            self.mode = 'disabled'
            print('W&B is not installed. Local events.jsonl still records all reward graphs.', flush=True)
            return
        if not configure_login(wandb, self.mode, prompt=prompt):
            if not settings['allow_offline_fallback']:
                raise RuntimeError('W&B online login is required by this preset; use the local login dialog or offline mode')
            self.mode = 'offline'
            self.last_logged = int(self.state.get('last_offline_update',
                self.state.get('last_update', -1) if previous_mode == 'offline' else -1))
            print('W&B runs offline. Sync the recorded run later to view it online.', flush=True)
        run_id = self.state.get('run_id') or uuid.uuid4().hex[:8]
        # offline W&B cannot resume an existing local spool; preserve the same logical
        # identity while SDK produces a new session directory and use monotonic steps.
        try:
            self.handle = wandb.init(project=settings['project'], entity=settings['entity'] or None,
                name=self.folder.name, id=run_id, resume='allow' if self.mode == 'online' else None,
                mode=self.mode, dir=str(self.folder), config=protocol,
                settings=wandb.Settings(init_timeout=30, quiet=True))
        except Exception:
            if not settings['allow_offline_fallback']:
                raise RuntimeError('W&B could not initialize; use offline mode or check connectivity') from None
            self.mode = 'disabled'
            print('W&B initialization failed. Training will record metrics locally.', flush=True)
            return
        for prefix in ('metrics/*', 'reward_components/*', 'weights/*', 'outcomes/*', 'evaluation/*', 'curriculum/*'):
            self.handle.define_metric(prefix, step_metric='train/update')
        for prefix in ('learning/*', 'performance/*', 'practice/*', 'reward_contributions/*', 'validation/*'):
            self.handle.define_metric(prefix, step_metric='train/update')
        for prefix in ('schema', 'reward_version', 'update', 'timesteps', 'train/*', 'metrics/weights/*',
                       'metrics/training/*', 'evaluation/seed_base', 'evaluation/evaluation'):
            self.handle.define_metric(prefix, hidden=True)
        self.last_logged = max(self.last_logged, int(getattr(self.handle, 'step', 0) or 0) - 1)
        self.state.update(run_id=run_id, mode=self.mode, project=settings['project'],
                          entity=settings['entity'], url=self.handle.url if self.mode == 'online' else None)
        atomic_json(self.statefile, self.state)
        if self.state.get('url'):
            print('W&B dashboard:', self.state['url'], flush=True)
        self._save_snapshot('config.json')
        self.thread = threading.Thread(target=self._worker, daemon=True, name='FreestyleWandb')
        self.thread.start()

    def _save_snapshot(self, filename):
        # The SDK may link/watch its source on Windows. Register a unique copy,
        # never a live file that the supervisor/native process replaces.
        source = self.folder / filename
        if not source.is_file():
            return
        try:
            self.snapshot_folder.mkdir(parents=True, exist_ok=True)
            snapshot = self.snapshot_folder / filename
            snapshot.write_bytes(source.read_bytes())
            self.handle.save(str(snapshot), base_path=str(self.folder), policy='now')
        except Exception:
            print('W&B file snapshot could not upload; the original remains in the run folder.', flush=True)

    def submit(self, event):
        if not self.handle or self.failed:
            return
        update = int(event.get('update', event.get('updates', event.get('total_updates', 0))))
        if update <= self.last_logged:
            return
        try:
            self.queue.put_nowait((update, deepcopy(event)))
        except queue.Full:
            # A stalled upload cannot build an unlimited RAM queue; durable native
            # events remain complete and can be uploaded with `monitor` afterward.
            print('W&B upload queue is full; full metrics remain in events.jsonl.', flush=True)

    def _worker(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                update, event = item
                if update <= self.last_logged:
                    continue
                self.handle.log(flatten_metrics(event), step=update)
                self.last_logged = update
                self.state['last_update'] = update
                self.state['last_' + self.mode + '_update'] = update
                atomic_json(self.statefile, self.state)
            except Exception:
                self.failed = True
                print('W&B upload interrupted; rewards and checkpoints continue saving locally.', flush=True)
            finally:
                self.queue.task_done()

    def close(self):
        if not self.handle:
            return
        # Never make a network outage delay safe pause. SDK flush is in a separate
        # daemon and the entire native event stream is preserved for later sync.
        try:
            self.queue.put(None, timeout=2)
        except queue.Full:
            return
        if self.thread:
            self.thread.join(timeout=8)
        def finish():
            try:
                for filename in ('latest.json', 'curriculum.json', 'progress.json'):
                    self._save_snapshot(filename)
                self.handle.finish()
            except Exception:
                pass
        worker = threading.Thread(target=finish, daemon=True)
        worker.start()
        worker.join(timeout=5)


class EventReader:
    def __init__(self, folder, offset=0):
        self.folder = Path(folder)
        self.path = self.folder / 'events.jsonl'
        self.offset = offset

    def read(self):
        if not self.path.is_file():
            return []
        result = []
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw or not raw.endswith(b'\n'):
                    self.offset = start
                    break
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise ValueError('Native metrics event is not a JSON object')
                result.append(event)
                self.offset = stream.tell()
        return result


def initialize(name, settings, build_dir=None, *, resume=False, continuation=None):
    folder = run_path(name)
    identity = binary_identity(build_dir)
    if resume:
        protocol = read_json(folder / 'protocol.json')
        if not protocol:
            raise FileNotFoundError('No Freestyle run to resume: ' + str(folder))
        if protocol['identity'] != identity:
            raise ValueError('This run belongs to another Freestyle build. Keep its files and use a new run name.')
        if sha256(folder / 'config.json') != protocol['config_sha256']:
            raise ValueError('Saved Freestyle configuration was edited; restore it or start a new isolated run')
        return folder, protocol
    if folder.exists():
        raise FileExistsError('Freestyle run exists; use Resume or choose a fresh run name')
    settings = validate_settings(settings)
    settings['run_name'] = name
    folder.mkdir(parents=True)
    atomic_json(folder / 'config.json', settings['native'])
    protocol = {'schema': SCHEMA, 'initialization': 'random_weights', 'settings': settings,
                'created_at': datetime.now(timezone.utc).isoformat(), 'identity': identity,
                'config_sha256': sha256(folder / 'config.json'),
                'runner_sha256': sha256(Path(__file__))}
    if continuation:
        protocol.update(initialization='policy_continuation_pending', parent_policy=continuation)
    atomic_json(folder / 'protocol.json', protocol)
    atomic_json(folder / 'progress.json', {'status': 'INITIALIZED', 'updates': 0, 'timesteps': 0})
    return folder, protocol


def completed_update(folder, fallback=0):
    """Budget starts at restored state, not a later unsaved metrics event."""
    updates = []
    for marker in (Path(folder) / 'checkpoints').glob('*/FREESTYLE_COMPLETE.json'):
        complete = read_json(marker, {})
        if type(complete.get('update')) is int and complete['update'] >= 0:
            updates.append(complete['update'])
    latest = read_json(Path(folder) / 'latest.json', {})
    if type(latest.get('update')) is int and latest['update'] >= 0:
        updates.append(latest['update'])
    return max(updates) if updates else int(fallback)


def fork_policy(name, parent, settings, build_dir=None, checkpoint=None):
    """Copy a completed compatible actor into a new reward experiment, read-only parent."""
    source = run_path(parent)
    if name == parent:
        raise ValueError('Continuation needs a different run name; the parent remains preserved')
    with process_lock(source.parent / (parent + '.lock')), process_lock(source.parent / (name + '.lock')):
        old = read_json(source / 'protocol.json', {})
        if old.get('schema') != SCHEMA:
            raise ValueError('Parent must be an existing Freestyle run')
        original = old['settings']['native']
        settings = validate_settings(settings)
        for key in ('width', 'depth', 'tick_skip', 'action_delay'):
            if original[key] != settings['native'][key]:
                raise ValueError('Continuation must preserve ' + key)
        backend = old['identity'].get('backend_sha', {})
        for filename in ('FreestyleObs.h', 'FreestyleActions.h'):
            if backend.get(filename) != sha256(HERE / filename):
                raise ValueError('Parent observation/action schema differs; refusing an incompatible actor')
        checkpoints = source / 'checkpoints'
        choices = [path for path in checkpoints.iterdir() if path.is_dir() and path.name.isdigit()
                   and (path / 'FREESTYLE_COMPLETE.json').is_file()]
        chosen = Path(checkpoint).resolve() if checkpoint else max(choices, key=lambda p: int(p.name), default=None)
        if chosen is None or not chosen.resolve().is_relative_to(checkpoints.resolve()):
            raise ValueError('No completed parent checkpoint found inside its checkpoint folder')
        marker = read_json(chosen / 'FREESTYLE_COMPLETE.json', {})
        saved = read_json(chosen / 'FREESTYLE_STATE.json', {})
        if marker.get('schema') != 1 or saved.get('schema') != 1 or \
                any(type(marker.get(k)) is not int or marker[k] < 0 for k in ('update', 'timesteps')) or \
                not isinstance(marker.get('source_sha'), str) or not marker['source_sha'] or \
                any(marker.get(k) != saved.get(k) for k in ('update', 'timesteps', 'source_sha')):
            raise ValueError('Parent checkpoint is incomplete or its state disagrees with the completion marker')
        policy = chosen / 'POLICY.lt'
        digest = sha256(policy)
        lineage = {'parent_run': parent, 'checkpoint': str(chosen.resolve()), 'policy_sha256': digest,
                   'parent_update': marker['update'], 'parent_timesteps': marker['timesteps'],
                   'observation_schema': 'slater_freestyle_flat512_v1',
                   'action_schema': 'slater_freestyle_94_stall_v1',
                   'critic': 'new for revised rewards', 'optimizers': 'new', 'reward_version': 2}
        folder, protocol = initialize(name, settings, build_dir, continuation=lineage)
        copy_folder = folder / 'parent_policy'
        copy_folder.mkdir()
        shutil.copyfile(policy, copy_folder / 'POLICY.lt')
        if sha256(policy) != digest or sha256(copy_folder / 'POLICY.lt') != digest:
            raise RuntimeError('Parent policy changed during copy; no continuation was launched')
        atomic_json(copy_folder / 'lineage.json', lineage)
        protocol.update(initialization='policy_continuation', parent_policy=lineage)
        atomic_json(folder / 'protocol.json', protocol)
        print('FREESTYLE_POLICY_FORK', json.dumps({'run': name, **lineage}), flush=True)
        return folder


def revised_reward_settings(parent):
    settings = validate_settings(read_json(run_path(parent) / 'protocol.json')['settings'])
    settings['native'].update(stage='contact_pop', difficulty=.25, rewards=reward_defaults(),
                              actor_lr=min(settings['native']['actor_lr'], .00005),
                              min_actor_lr=.00001, critic_warmup_updates=10)
    return validate_settings(settings)


def write_progress(folder, progress):
    """A locked dashboard status file must not stop the native learner."""
    try:
        atomic_json(Path(folder) / 'progress.json', progress)
        return True
    except PermissionError as exc:
        if getattr(exc, 'winerror', None) not in (5, 32, 33):
            raise
        print('FREESTYLE_STATUS_WARNING progress.json is locked; native training continues. '
              'The latest metrics remain in events.jsonl; status will retry at the next update.', flush=True)
        return False


def train(name, settings, build_dir=None, meshes=None, *, resume=False, updates=None, mode=None):
    from GigaLearn_Project.Native_Backend import native_setup as helper
    folder = run_path(name)
    folder.parent.mkdir(parents=True, exist_ok=True)
    # Lock lives beside the run, so acquiring it cannot make a new run look existing.
    with process_lock(folder.parent / (name + '.lock')), process_lock(folder.parent / (name + '.telemetry.lock')):
        folder, protocol = initialize(name, settings, build_dir, resume=resume)
        if protocol.get('initialization') == 'policy_continuation_pending':
            raise RuntimeError('Actor copy was interrupted. Keep the parent and create a continuation with a new run name; refusing random initialization.')
        monitor_settings = deepcopy(protocol['settings']['wandb'])
        if mode is not None:
            monitor_settings['mode'] = mode
        reader = EventReader(folder)
        previous = read_json(folder / 'progress.json', {})
        native_config = read_json(folder / 'config.json')
        if updates is not None:
            if not 0 <= updates <= 10000000:
                raise ValueError('updates must be 0 (unlimited) or a positive additional update budget')
            restored_update = completed_update(folder, previous.get('updates', 0))
            native_config['max_updates'] = 0 if updates == 0 else restored_update + updates
        atomic_json(folder / 'launch_config.json', native_config)
        pause = folder / 'PAUSE'
        pause.unlink(missing_ok=True)
        binary = binary_path(build_dir)
        mesh_path = Path(meshes).resolve() if meshes else helper.meshes()
        args = [str(binary), '--config', str(folder / 'launch_config.json'), '--out', str(folder),
                '--meshes', str(mesh_path), '--pause', str(pause)]
        parent = protocol.get('parent_policy')
        has_checkpoint = any((folder / 'checkpoints').glob('*/FREESTYLE_COMPLETE.json'))
        if parent and not has_checkpoint:
            copied = folder / 'parent_policy'
            if sha256(copied / 'POLICY.lt') != parent['policy_sha256']:
                raise ValueError('Copied continuation actor changed; restore the preserved copy')
            args += ['--warm-start', str(copied)]
        elif resume:
            args.append('--resume')
        environment = helper.runtime_environment(binary, pause)
        for key in REDACT_ENV:
            environment.pop(key, None)
        environment['PYTHONUNBUFFERED'] = '1'
        # Resolve/validate the native prerequisites before opening an online run.
        monitor = WandbMonitor(folder, monitor_settings, protocol)
        logfile = folder / ('native_' + str(time.time_ns()) + '.log')
        print('FREESTYLE_RUN', name, 'continuing preserved actor with revised rewards' if parent else
              ('random initialization' if not resume else 'resuming saved weights/optimizer/curriculum'), flush=True)
        print('Checkpoint/reward files:', folder, flush=True)
        process = None
        try:
            with logfile.open('wb') as output:
                options = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                process = subprocess.Popen(args, cwd=binary.parent, env=environment, stdout=output, stderr=subprocess.STDOUT, **options)
                write_progress(folder, {**previous, 'status': 'TRAINING', 'pid': process.pid,
                                       'runner_pid': os.getpid(), 'native_log': str(logfile)})
                while True:
                    events = reader.read()
                    for event in events:
                        monitor.submit(event)
                        update = int(event.get('update', event.get('updates', event.get('total_updates', 0))))
                        stage = event.get('stage', event.get('curriculum', {}).get('stage', '?'))
                        progress = {'status': 'TRAINING', 'updates': update,
                            'timesteps': int(event.get('timesteps', event.get('total_timesteps', 0))),
                            'stage': stage, 'event': event, 'pid': process.pid, 'runner_pid': os.getpid(),
                            'native_log': str(logfile), 'wandb_url': monitor.state.get('url')}
                        write_progress(folder, progress)
                        print('FREESTYLE_UPDATE', json.dumps(event, separators=(',', ':')), flush=True)
                    code = process.poll()
                    if code is not None:
                        # One final pass after the writer closes handles the final report.
                        for event in reader.read():
                            monitor.submit(event)
                            write_progress(folder, {'status': 'TRAINING',
                                'updates': int(event.get('update', event.get('updates', 0))),
                                'timesteps': int(event.get('timesteps', 0)), 'event': event,
                                'stage': event.get('stage', '?'), 'native_log': str(logfile)})
                        break
                    try:
                        time.sleep(.2)
                    except KeyboardInterrupt:
                        pause.write_text('Safe pause requested by Ctrl+C\n', encoding='utf-8')
                        print('Safe pause requested; waiting for the native checkpoint boundary.', flush=True)
                with logfile.open('rb') as tail_stream:
                    tail_stream.seek(max(0, logfile.stat().st_size - 24000))
                    tail = tail_stream.read().decode('utf-8', errors='replace')[-12000:]
            if code:
                raise RuntimeError(f'Freestyle native process exited {code}; inspect {logfile}\n' + tail[-4000:])
            markers = re.findall(r'^FREESTYLE_COMPLETE\s+(\{[^\n]+\})', tail, re.MULTILINE)
            if not markers:
                raise RuntimeError('Native worker returned without a completion marker; inspect ' + str(logfile))
            completion = json.loads(markers[-1])
            status = completion.get('status', 'PAUSED' if pause.exists() else 'COMPLETE')
            progress = read_json(folder / 'progress.json', {})
            progress.update(status=status, completion=completion, latest=read_json(folder / 'latest.json', {}),
                            wandb_url=monitor.state.get('url'),
                            updates=int(completion.get('total_updates', completion.get('updates', progress.get('updates', 0)))),
                            timesteps=int(completion.get('timesteps', completion.get('total_timesteps', progress.get('timesteps', 0)))))
            write_progress(folder, progress)
            print('FREESTYLE_JOB_COMPLETE', json.dumps(completion), flush=True)
            return progress
        except KeyboardInterrupt:
            if process is not None and process.poll() is None:
                stop_native_safely(process, pause)
            progress = read_json(folder / 'progress.json', {})
            completion = read_json(folder / 'status.json', {})
            progress.update(status=completion.get('status', 'PAUSED'), completion=completion,
                            latest=read_json(folder / 'latest.json', {}), native_log=str(logfile),
                            updates=int(completion.get('total_updates', progress.get('updates', 0))),
                            timesteps=int(completion.get('timesteps', progress.get('timesteps', 0))))
            write_progress(folder, progress)
            print('FREESTYLE_JOB_COMPLETE', json.dumps(completion or {'status': progress['status']}), flush=True)
            return progress
        except BaseException as exc:
            if process is not None and process.poll() is None:
                stop_native_safely(process, pause)
            progress = read_json(folder / 'progress.json', {})
            write_progress(folder, {**progress, 'status': 'ERROR', 'native_log': str(logfile),
                                    'error_type': type(exc).__name__})
            raise
        finally:
            monitor.close()


def stop_native_safely(process, pause, grace_seconds=120):
    """Hold the caller's run lock until its native child actually stops."""
    Path(pause).write_text('Safe pause requested by the Python supervisor\n', encoding='utf-8')
    print('Waiting for the native checkpoint boundary before releasing this run.', flush=True)
    deadline = time.monotonic() + grace_seconds
    while process.poll() is None:
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                print('Native worker did not reach a pause boundary. Stopping it; the last completed checkpoint remains preserved.', flush=True)
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
        except KeyboardInterrupt:
            # A second Ctrl+C cannot release the lock while the child writes.
            continue


def pause_run(name):
    folder = run_path(name)
    if not (folder / 'protocol.json').is_file():
        raise FileNotFoundError('No Freestyle run named ' + name)
    (folder / 'PAUSE').write_text('Safe pause requested locally\n', encoding='utf-8')
    print('Safe pause requested. Wait for PAUSED before copying/rebuilding.', flush=True)


def status(name):
    folder = run_path(name)
    return {'run': str(folder), 'progress': read_json(folder / 'progress.json', {}),
            'latest': read_json(folder / 'latest.json', {}),
            'curriculum': read_json(folder / 'curriculum.json', {}),
            'wandb': read_json(folder / 'wandb_state.json', {})}


def mechanics_catalogue():
    catalogue = read_json(ROOT / 'FREESTYLE_MECHANICS.json')
    if not catalogue or catalogue.get('schema') != 'slater-freestyle-mechanics-v1':
        raise ValueError('Freestyle mechanics catalogue is missing or incompatible')
    return catalogue


def monitor_saved(name, mode=None):
    folder = run_path(name)
    protocol = read_json(folder / 'protocol.json')
    if not protocol:
        raise FileNotFoundError('No saved run')
    settings = deepcopy(protocol['settings']['wandb'])
    if mode:
        settings['mode'] = mode
    with process_lock(folder.parent / (name + '.telemetry.lock')):
        monitor = WandbMonitor(folder, settings, protocol)
        try:
            for event in EventReader(folder).read():
                # Retrospective upload may wait for the bounded telemetry queue.
                if monitor.handle:
                    update = int(event.get('update', event.get('updates', 0)))
                    if update > monitor.last_logged:
                        monitor.queue.put((update, event), timeout=30)
            print('Recorded metric upload queued. Local source:', folder / 'events.jsonl', flush=True)
        finally:
            monitor.close()


def desktop(settings_file=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
    import webbrowser
    settings = validate_settings(read_json(settings_file) if settings_file else defaults())
    root = tk.Tk()
    root.title('Slater Freestyle — from scratch')
    root.geometry('930x760')
    name = tk.StringVar(value=settings['run_name'])
    mode = tk.StringVar(value=settings['wandb']['mode'])
    headline = tk.StringVar(value='New independent model · original models remain in their own runs')
    row = ttk.Frame(root, padding=10); row.pack(fill='x')
    ttk.Label(row, text='Run').pack(side='left')
    ttk.Entry(row, textvariable=name, width=32).pack(side='left', padx=8)
    ttk.Label(row, text='W&B').pack(side='left')
    ttk.Combobox(row, textvariable=mode, values=('online', 'offline', 'disabled'), width=10, state='readonly').pack(side='left', padx=8)
    ttk.Label(root, text='Online first start opens a local password dialog. Ctrl+V pastes the key; it never enters settings.').pack(anchor='w', padx=12)
    ttk.Label(root, textvariable=headline, wraplength=890).pack(anchor='w', padx=12, pady=8)
    editor = tk.Text(root, height=21, wrap='none', font=('Consolas', 10))
    editor.pack(fill='both', expand=True, padx=12)
    editor.insert('1.0', json.dumps(settings, indent=2))
    summary = tk.Text(root, height=10, wrap='word', font=('Consolas', 9), state='disabled')
    summary.pack(fill='both', padx=12, pady=8)
    job = {'process': None, 'log': None}

    def current():
        value = json.loads(editor.get('1.0', 'end'))
        value['run_name'], value['wandb']['mode'] = name.get(), mode.get()
        return validate_settings(value)

    def show_error(exc):
        messagebox.showerror('Freestyle', str(exc), parent=root)

    def start(command, updates=None):
        try:
            if job['process'] and job['process'].poll() is None:
                raise RuntimeError('The current job is running; safely pause it first')
            value = current()
            ui_settings = BASE / 'desktop_settings.json'
            atomic_json(ui_settings, value)
            args = [sys.executable, '-u', str(Path(__file__)), command, '--settings', str(ui_settings)]
            if command in ('train', 'resume'):
                args += ['--run', value['run_name'], '--wandb-mode', mode.get()]
                if updates is not None:
                    args += ['--updates', str(updates)]
            elif command == 'smoke':
                args += ['--wandb-mode', 'disabled']
            logdir = BASE / 'app_logs'; logdir.mkdir(parents=True, exist_ok=True)
            logfile = logdir / (str(time.time_ns()) + '_' + command + '.log')
            options = {'cwd': str(ROOT)}
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            with logfile.open('wb') as output:
                job['process'] = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, **options)
            job['log'] = logfile
            headline.set(command.capitalize() + ' running. Closing this window leaves the job running; use Safe pause to stop at a checkpoint.')
        except Exception as exc:
            show_error(exc)

    def do_pause():
        try:
            pause_run(name.get())
            headline.set('Safe pause requested; native PPO finishes its current update and saves.')
        except Exception as exc:
            show_error(exc)

    def continue_revised():
        try:
            if job['process'] and job['process'].poll() is None:
                raise RuntimeError('Safely pause the current training job first')
            parent = name.get()
            child = simpledialog.askstring('Continue with revised rewards',
                'New run name (the current run is preserved):', initialvalue='freestyle_rewards02', parent=root)
            if not child:
                return
            value = revised_reward_settings(parent)
            value['run_name'] = child
            fork_policy(child, parent, value)
            name.set(child)
            editor.delete('1.0', 'end'); editor.insert('1.0', json.dumps(value, indent=2))
            start('resume', updates=200)
        except Exception as exc:
            show_error(exc)

    def import_settings():
        path = filedialog.askopenfilename(filetypes=(('Freestyle JSON', '*.json'),))
        if path:
            try:
                value = validate_settings(read_json(path))
                editor.delete('1.0', 'end'); editor.insert('1.0', json.dumps(value, indent=2))
                name.set(value['run_name']); mode.set(value['wandb']['mode'])
            except Exception as exc:
                show_error(exc)

    def export_settings():
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=(('Freestyle JSON', '*.json'),))
        if path:
            try:
                atomic_json(path, current())
            except Exception as exc:
                show_error(exc)

    def open_dashboard():
        url = read_json(run_path(name.get()) / 'wandb_state.json', {}).get('url')
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo('W&B', 'The dashboard link appears after an online run starts. Offline rewards remain in events.jsonl.', parent=root)

    def open_mechanics():
        try:
            catalogue = mechanics_catalogue()
            window = tk.Toplevel(root)
            window.title('Freestyle mechanics — objectives and roadmap')
            window.geometry('1050x620')
            ttk.Label(window, text='Implemented events and proxies are training objectives. Planned names have no dedicated detector yet.',
                      wraplength=1000).pack(anchor='w', padx=10, pady=8)
            table = ttk.Treeview(window, columns=('name', 'family', 'status', 'stage'), show='headings')
            for column, width in (('name', 260), ('family', 160), ('status', 210), ('stage', 180)):
                table.heading(column, text=column.capitalize())
                table.column(column, width=width)
            table.pack(fill='both', expand=True, padx=10)
            by_id = {}
            for entry in catalogue['mechanics']:
                by_id[entry['id']] = entry
                table.insert('', 'end', iid=entry['id'], values=(entry['name'], entry['family'], entry['status'], entry['stage'] or '—'))
            detail = tk.StringVar(value='Select a mechanic to see the detection requirements.')
            ttk.Label(window, textvariable=detail, wraplength=1000).pack(fill='x', padx=10, pady=12)
            def select(_event):
                picked = table.selection()
                if picked:
                    entry = by_id[picked[0]]
                    detail.set(entry['verification'])
            table.bind('<<TreeviewSelect>>', select)
        except Exception as exc:
            show_error(exc)

    controls = ttk.Frame(root, padding=10); controls.pack(fill='x')
    for label, callback in (('Build', lambda: start('build')), ('Smoke (2 updates)', lambda: start('smoke')),
                            ('Start new', lambda: start('train')), ('Resume', lambda: start('resume')),
                            ('Safe pause', do_pause), ('W&B dashboard', open_dashboard),
                            ('Import settings', import_settings), ('Export settings', export_settings)):
        ttk.Button(controls, text=label, command=callback).pack(side='left', padx=3)
    ttk.Button(root, text='Mechanics catalogue', command=open_mechanics).pack(anchor='w', padx=12, pady=(0, 8))
    ttk.Button(root, text='Continue with revised rewards', command=continue_revised).pack(anchor='w', padx=12, pady=(0, 8))

    def poll():
        try:
            value = status(name.get())
            if job['process'] and job['process'].poll() is not None:
                headline.set('Job ended with exit code ' + str(job['process'].returncode) + '; see the saved run status/log below.')
                job['process'] = None
            text = json.dumps(value, indent=2)
            if job['log']:
                with job['log'].open('rb') as stream:
                    stream.seek(max(0, job['log'].stat().st_size - 12000))
                    tail = stream.read().decode('utf-8', errors='replace')
                text += '\n\nJob log: ' + str(job['log']) + '\n' + tail[-6000:]
            summary.configure(state='normal'); summary.delete('1.0', 'end'); summary.insert('1.0', text); summary.configure(state='disabled')
        except Exception:
            pass
        root.after(1500, poll)
    root.after(100, poll)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check-build', 'smoke', 'train', 'resume', 'fork', 'pause', 'status', 'monitor', 'gui', 'settings', 'mechanics'))
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--run')
    parser.add_argument('--from-run')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--giga-source', type=Path)
    parser.add_argument('--meshes', type=Path)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--updates', type=int)
    parser.add_argument('--wandb-mode', choices=('online', 'offline', 'disabled'))
    args = parser.parse_args()
    settings = validate_settings(read_json(args.settings) if args.settings else defaults())
    name = args.run or settings['run_name']
    if args.command == 'build':
        build(args.build_dir, args.giga_source, args.jobs)
    elif args.command == 'check-build':
        print(json.dumps(binary_identity(args.build_dir)))
    elif args.command == 'gui':
        desktop(args.settings)
    elif args.command == 'settings':
        print(json.dumps(settings, indent=2))
    elif args.command == 'mechanics':
        print(json.dumps(mechanics_catalogue(), indent=2, ensure_ascii=False))
    elif args.command == 'pause':
        pause_run(name)
    elif args.command == 'status':
        print(json.dumps(status(name), indent=2))
    elif args.command == 'monitor':
        monitor_saved(name, args.wandb_mode)
    elif args.command == 'fork':
        if not args.from_run or not args.run:
            parser.error('fork requires --from-run PARENT --run NEW_NAME')
        value = settings if args.settings else revised_reward_settings(args.from_run)
        fork_policy(name, args.from_run, value, args.build_dir, args.checkpoint)
    else:
        if args.command == 'smoke':
            name = args.run or ('smoke_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
            settings['native'].update(games=4, steps_per_update=1024, minibatch=512,
                                      epochs=1, max_updates=2, device='cpu', eval_every_updates=1,
                                      eval_episodes=4)
        train(name, settings, args.build_dir, args.meshes, resume=args.command == 'resume',
              updates=args.updates, mode=args.wandb_mode or ('disabled' if args.command == 'smoke' else None))


if __name__ == '__main__':
    main()
