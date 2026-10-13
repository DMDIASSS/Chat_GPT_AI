"""Desktop control center for isolated attention training and model selection.

Importing this module does not import Torch or start training. Processes write
directly to durable files, so closing the window can leave a job running.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/isolated/training_studio'
ROUTINES = ('match', 'defense', 'wall-reset', 'air-control', 'recovery', 'boost', 'bump', 'bump-evasion')
NATIVE_FLAGS = {'games', 'steps', 'device', 'seed', 'actor_lr', 'critic_lr', 'target_kl',
                'teacher_weight', 'seconds', 'eval_seeds', 'curriculum', 'start_stage',
                'practice_fraction', 'practice_anchor', 'curriculum_difficulty',
                'routine', 'formats', 'selfplay_refresh', 'opponent_pool'}
RUN_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SECRET_KEY = re.compile(r'(?:^|_)(?:token|password|secret|api_key|authorization)(?:$|_)', re.I)
CAMPAIGN_COMMON = {'cycles': 8, 'chunk_updates': 20, 'branch_updates': 100,
                   'plateau_chunks': 3, 'screen_every': 5, 'max_minutes': 0.,
                   'unlimited_until_paused': False}


def default_settings():
    source = 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
    return {
        'source': source, 'selection': '', 'build_dir': '',
        'native_run': 'studio_attention01', 'selector_run': 'studio_selection01',
        'campaign_run': 'studio_campaign01', 'updates': 100, 'checkpoint': '',
        'eval_seeds': 8, 'eval_seconds': 60., 'max_games': 512, 'until': 'screen',
        'export_name': 'StudioChampion01', 'export_kickoff': 'both',
        'native_profile': {'games': 8, 'steps': 128, 'device': 'auto', 'seed': 20261013,
                           'actor_lr': 3e-6, 'critic_lr': 1e-4, 'target_kl': .005,
                           'teacher_weight': .1, 'seconds': 12., 'eval_seeds': 2,
                           'routine': 'match', 'formats': '1v1,2v2,3v3',
                           'selfplay_refresh': 10},
        'selector': {},
        'campaign': deepcopy(CAMPAIGN_COMMON),
        'replays': {'inputs': 'data/replays/ranked-duels',
                    'output': 'data/isolated/studio_replays01', 'workers': 2,
                    'max_replays': 100, 'per_replay': 1024, 'max_samples': 100000,
                    'prepared': 'data/isolated/event_curriculum/windows01',
                    'audit_checkpoint': '', 'raw_count': 4, 'audit_run': 'studio_replay_audit01'},
    }


def resolve_path(value, root=ROOT):
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(root) / path


def source_file(value, root=ROOT):
    path = resolve_path(value, root)
    if path.is_dir():
        if not ((path / 'COMPLETE').is_file() or (path / 'COMPLETE.json').is_file()):
            raise ValueError('Choose a completed native checkpoint folder')
        path /= 'actor.pt'
    if not path.is_file():
        raise FileNotFoundError('Model does not exist: ' + str(path))
    if path.suffix.lower() != '.pt':
        raise ValueError('Choose an attention .pt checkpoint or a completed native checkpoint folder')
    return path


def forbid_credentials(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY.search(str(key)):
                raise ValueError('Studio settings cannot store credentials: ' + str(key))
            forbid_credentials(child)
    elif isinstance(value, list):
        for child in value:
            forbid_credentials(child)


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError('Settings must be a JSON object')
    allowed = set(default_settings())
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError('Unknown Studio settings: ' + ', '.join(sorted(unknown)))
    result = {**default_settings(), **deepcopy(settings)}
    forbid_credentials(result)
    for key in ('native_run', 'selector_run', 'campaign_run'):
        if not isinstance(result[key], str) or not RUN_NAME.fullmatch(result[key]):
            raise ValueError('Run names use 1–64 ASCII letters, numbers, underscores or hyphens')
    if len(result['campaign_run']) > 40:
        raise ValueError('Campaign names use at most 40 characters to leave room for branch names')
    for key, low, high in (('updates', 1, 100000), ('eval_seeds', 1, 64), ('max_games', 1, 100000)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f'{key} must be an integer from {low} to {high}')
    if type(result['eval_seconds']) not in (int, float) or not math.isfinite(result['eval_seconds']) or not 3 <= result['eval_seconds'] <= 300:
        raise ValueError('Evaluation duration must be 3–300 seconds')
    if result['until'] not in ('screen', 'refine', 'finalists', 'confirm'):
        raise ValueError('Unknown selection stage')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,48}', result['export_name']):
        raise ValueError('Export names use 1–49 ASCII letters, numbers, underscores or hyphens')
    if result['export_kickoff'] not in ('learned', 'scripted', 'both'):
        raise ValueError('Export kickoff must be learned, scripted or both')
    for key in ('native_profile', 'selector', 'campaign', 'replays'):
        if not isinstance(result[key], dict):
            raise ValueError(key + ' must be a JSON object')
    result['campaign'] = {**deepcopy(CAMPAIGN_COMMON), **result['campaign']}
    unknown = set(result['native_profile']) - NATIVE_FLAGS
    if unknown:
        raise ValueError('Unknown native profile fields: ' + ', '.join(sorted(unknown)))
    profile = result['native_profile']
    if profile.get('device', 'auto') not in ('auto', 'cpu', 'cuda'):
        raise ValueError('Choose auto, cpu or cuda')
    if profile.get('routine', 'match') not in ROUTINES:
        raise ValueError('Unknown training routine')
    for key, low, high in (('games', 1, 128), ('steps', 16, 4096), ('selfplay_refresh', 0, 10000)):
        if key in profile and (type(profile[key]) is not int or not low <= profile[key] <= high):
            raise ValueError(f'{key} must be an integer from {low} to {high}')
    for key in ('actor_lr', 'critic_lr', 'target_kl', 'teacher_weight', 'practice_fraction',
                'practice_anchor', 'curriculum_difficulty', 'seconds'):
        if key in profile and (type(profile[key]) not in (int, float) or not math.isfinite(profile[key])):
            raise ValueError(key + ' must be finite')
    for key, low, high in (('actor_lr', 1e-8, 5e-5), ('critic_lr', 1e-7, .001),
                           ('target_kl', .0001, .05), ('teacher_weight', 0., 1.),
                           ('seconds', 3., 300.)):
        if key in profile and not low <= profile[key] <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if isinstance(profile.get('formats'), list):
        profile['formats'] = ','.join(str(fmt) for fmt in profile['formats'])
    replay_defaults = default_settings()['replays']
    if set(result['replays']) - set(replay_defaults):
        raise ValueError('Unknown replay preparation setting')
    result['replays'] = {**replay_defaults, **result['replays']}
    replay = result['replays']
    for key, low, high in (('workers', 1, 8), ('max_replays', 1, 10000), ('per_replay', 48, 10000),
                           ('max_samples', 100, 2000000), ('raw_count', 0, 500)):
        if type(replay[key]) is not int or not low <= replay[key] <= high:
            raise ValueError(f'Replay {key} must be an integer from {low} to {high}')
    if not isinstance(replay['audit_run'], str) or not RUN_NAME.fullmatch(replay['audit_run']):
        raise ValueError('Use a simple replay audit run name')
    return result


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def child_python():
    # pythonw starts the GUI; python.exe gives the workers reliable stdio.
    console = Path(sys.executable).with_name('python.exe')
    return str(console if os.name == 'nt' and console.is_file() else Path(sys.executable))


def native_profile_args(profile):
    args = []
    for key, value in profile.items():
        if value is not None and value != '':
            args += ['--' + key.replace('_', '-'), str(value)]
    return args


def command_for(engine, action, settings, *, config_file=None, root=ROOT, interpreter=None):
    """Return argv, never shell text; checkpoint paths remain single arguments."""
    cfg = validate_settings(settings)
    root = Path(root)
    python = interpreter or child_python()
    scripts = {'native': 'slater_native_attention.py', 'selector': 'slater_model_selection.py',
               'campaign': 'slater_champion_campaign.py'}
    if engine == 'replay':
        options = cfg['replays']
        inputs = resolve_path(options['inputs'], root)
        if action == 'prepare':
            output = resolve_path(options['output'], root).resolve()
            if not output.is_relative_to((root / 'data/isolated').resolve()):
                raise ValueError('Prepared replay data must remain inside data/isolated')
            return [python, str(root / 'slater_versatile_trainer.py'), 'prepare',
                    '--inputs', str(inputs), '--out', str(output),
                    '--workers', str(options['workers']), '--max-replays', str(options['max_replays']),
                    '--per-replay', str(options['per_replay']), '--max-samples', str(options['max_samples'])]
        if action == 'audit':
            command = [python, str(root / 'slater_replay_input_audit.py'),
                       '--prepared', str(resolve_path(options['prepared'], root)), '--inputs', str(inputs),
                       '--raw-count', str(options['raw_count']), '--run', options['audit_run']]
            if options['audit_checkpoint']:
                command += ['--checkpoint', str(resolve_path(options['audit_checkpoint'], root))]
            return command
        raise ValueError('Replay tools support preparation and audit')
    if engine == 'export':
        source = source_file(cfg['source'], root)
        return [python, str(root / 'slater_training_studio.py'), '--worker-export',
                '--source', str(source), '--export-name', cfg['export_name'],
                '--export-kickoff', cfg['export_kickoff']]
    if engine not in scripts:
        raise ValueError('Unknown operation')
    if engine == 'selector' and action == 'run':
        existing = root / 'data/isolated/model_selection/runs' / cfg['selector_run'] / 'config.json'
        if existing.is_file():
            # Inventory already initialized the immutable selector protocol.
            action = 'resume'
    allowed = {'native': ('build', 'parity', 'smoke', 'train', 'resume', 'pause', 'status', 'eval', 'export'),
               'selector': ('inventory', 'run', 'resume', 'pause', 'status', 'rank'),
               'campaign': ('run', 'resume', 'pause', 'status')}
    if action not in allowed[engine]:
        raise ValueError('Unsupported operation')
    if engine == 'native' and action == 'build':
        command = [python, str(root / 'slater_training_studio.py'), '--worker-build']
        if cfg['build_dir']:
            command += ['--build-dir', str(resolve_path(cfg['build_dir'], root))]
        return command
    run = cfg[{'native': 'native_run', 'selector': 'selector_run', 'campaign': 'campaign_run'}[engine]]
    command = [python, str(root / scripts[engine]), action, '--run', run]
    if action in ('pause', 'status'):
        return command
    if cfg['build_dir']:
        command += ['--build-dir', str(resolve_path(cfg['build_dir'], root))]
    if action == 'rank':
        return command
    if engine == 'selector':
        if action != 'resume':
            if config_file is None:
                raise ValueError('A saved selector configuration is required')
            command += ['--config', str(config_file)]
        if action != 'inventory':
            command += ['--max-games', str(cfg['max_games']), '--until', cfg['until']]
        return command
    if engine == 'campaign':
        if action == 'run':
            if config_file is None:
                raise ValueError('A saved campaign configuration is required')
            command += ['--config', str(config_file)]
            if cfg['selection']:
                command += ['--selection', str(resolve_path(cfg['selection'], root))]
            else:
                command += ['--source', str(source_file(cfg['source'], root))]
        return command
    if action == 'eval':
        command += ['--eval-seeds', str(cfg['eval_seeds']), '--seconds', str(cfg['eval_seconds'])]
    if action in ('eval', 'export') and cfg['checkpoint']:
        command += ['--checkpoint', str(resolve_path(cfg['checkpoint'], root))]
    if action == 'resume':
        command += ['--updates', str(cfg['updates'])]
    if action in ('train', 'parity', 'smoke'):
        if cfg['selection'] and action == 'train':
            command += ['--selection', str(resolve_path(cfg['selection'], root))]
        else:
            command += ['--source', str(source_file(cfg['source'], root))]
        if action == 'train':
            command += ['--updates', str(cfg['updates'])]
        command += native_profile_args(cfg['native_profile'])
    return command


def discover_checkpoints(root=ROOT):
    """Read names/markers only; model tensors are checked by the backend."""
    root = Path(root)
    entries = []
    families = {'Mechanics': root / 'data/isolated/mechanics_curriculum/selected7_mechanics01',
                'Team': root / 'data/isolated/team_campaigns',
                'Attention': root / 'data/isolated/native_attention/runs'}
    for family, base in families.items():
        if not base.is_dir():
            continue
        patterns = ('update_*.pt', 'accepted*.pt') if family == 'Mechanics' else ('**/update_*.pt',)
        if family == 'Attention':
            patterns = ('*/checkpoints/checkpoint_*/actor.pt',)
        seen = set()
        for pattern in patterns:
            for path in base.glob(pattern):
                if path in seen or not path.is_file():
                    continue
                seen.add(path)
                if family == 'Attention' and not ((path.parent / 'COMPLETE').is_file() or (path.parent / 'COMPLETE.json').is_file()):
                    continue
                entries.append({'family': family, 'name': path.parent.name if family == 'Attention' else path.name,
                                'path': str(path), 'bytes': path.stat().st_size})
    return sorted(entries, key=lambda row: (row['family'], row['path']))


def progress_from_line(line):
    """Extract structured progress without inventing strength from losses."""
    left, separator, right = line.strip().partition(' ')
    if not separator or not left.startswith(('SLATER_', 'ATTENTION_', 'MODEL_SELECTION_', 'CHAMPION_')):
        return None
    try:
        payload = json.loads(right)
    except ValueError:
        return None
    return {'marker': left, **payload} if isinstance(payload, dict) else None


def process_identity(pid):
    """Check existence plus creation time; never signal a Windows process."""
    if type(pid) is not int or pid < 1:
        return None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *(ctypes.POINTER(wintypes.FILETIME) for _ in range(4)))
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                return None
            creation, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exited),
                                          ctypes.byref(system), ctypes.byref(user)):
                return None
            return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        tail = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if tail[0] == 'Z':
            return None
        return tail[19]
    except (OSError, IndexError):
        return None


class DetachedProcess:
    def __init__(self, job):
        self.pid = job['pid']
        self.identity = job['process_identity']
        self.result_path = Path(job['result'])
        self.returncode = None

    def poll(self):
        result = read_json(self.result_path)
        if 'returncode' in result:
            self.returncode = result['returncode']
        elif process_identity(self.pid) != self.identity:
            self.returncode = -1
        return self.returncode


def result_directory(engine, run, root=ROOT):
    bases = {'native': 'data/isolated/native_attention/runs',
             'selector': 'data/isolated/model_selection/runs',
             'campaign': 'data/isolated/champion_campaigns'}
    if engine not in bases or not RUN_NAME.fullmatch(run):
        raise ValueError('Unknown result location')
    return Path(root) / bases[engine] / run


def campaign_champion(settings, root=ROOT):
    selection = read_json(result_directory('campaign', settings['campaign_run'], root) / 'selected.json')
    if not selection.get('actor_path'):
        raise ValueError('No saved campaign champion is available yet')
    path = source_file(selection['actor_path'], root)
    expected = selection.get('exported_sha256')
    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('The saved champion actor changed; inspect the campaign report')
    return path


def job_config(engine, settings):
    options = deepcopy(settings[engine])
    if engine == 'selector':
        options.setdefault('device', settings['native_profile']['device'])
    elif engine == 'campaign':
        profile = options.setdefault('native_profile', {})
        for key, value in settings['native_profile'].items():
            profile.setdefault(key, value)
    else:
        raise ValueError('This operation does not use a configuration JSON')
    return options


def format_preset(settings, all_nine=False):
    result = deepcopy(settings)
    formats = [f'{ours}v{theirs}' for ours in range(1, 4) for theirs in range(1, 4)] if all_nine else ['1v1', '2v2', '3v3']
    result['native_profile']['formats'] = ','.join(formats)
    result['campaign']['formats'] = formats
    result['campaign']['mode_weights'] = {mode: 1 / len(formats) for mode in formats}
    if 'native_profile' in result['campaign']:
        result['campaign']['native_profile']['formats'] = ','.join(formats)
    return validate_settings(result)


class ProcessManager:
    """Own one foreground job while preserving safe detached child output."""
    def __init__(self, root=ROOT, base=None):
        self.root = Path(root)
        self.base = Path(base or self.root / 'data/isolated/training_studio')
        self.process = None
        self.job = None
        self._lock = threading.Lock()
        previous = read_json(self.base / 'last_job.json')
        if previous.get('process_identity') and previous.get('result'):
            recovered = DetachedProcess(previous)
            if recovered.poll() is None:
                self.process, self.job = recovered, previous

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def start(self, argv, engine, action, run):
        with self._lock:
            if self.active:
                raise RuntimeError('A job is already running; pause it before starting another')
            if not isinstance(argv, list) or any(not isinstance(arg, str) for arg in argv):
                raise TypeError('Jobs require a string argument list')
            self.base.mkdir(parents=True, exist_ok=True)
            logfile = self.base / 'logs' / f'{time.time_ns()}_{engine}_{action}.log'
            logfile.parent.mkdir(parents=True, exist_ok=True)
            specification = self.base / 'jobs' / (logfile.stem + '.json')
            result = specification.with_suffix('.result.json')
            atomic_json(specification, {'argv': argv, 'result': str(result), 'root': str(self.root)})
            wrapper = [child_python(), str(self.root / 'slater_training_studio.py'),
                       '--worker-job', str(specification)]
            environment = os.environ.copy()
            environment['PYTHONUNBUFFERED'] = '1'
            options = {'cwd': self.root, 'env': environment}
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            with logfile.open('wb') as output:
                self.process = subprocess.Popen(wrapper, stdout=output, stderr=subprocess.STDOUT, **options)
            self.job = {'engine': engine, 'action': action, 'run': run, 'pid': self.process.pid,
                        'argv': argv, 'log': str(logfile), 'started_at': datetime.now(timezone.utc).isoformat()}
            self.job.update(process_identity=process_identity(self.process.pid), result=str(result))
            atomic_json(self.base / 'last_job.json', self.job)
            return self.job

    def request_pause(self, argv):
        if not self.active:
            raise RuntimeError('No active job to pause')
        if self.job['action'] not in ('train', 'resume', 'run', 'inventory'):
            raise ValueError('This short operation has no pause boundary; let it finish')
        options = {'cwd': self.root, 'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT,
                   'text': True, 'encoding': 'utf-8', 'errors': 'replace'}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(argv, **options)
        if completed.returncode:
            raise RuntimeError(completed.stdout.strip() or 'Pause request failed')
        return completed.stdout.strip()


def visual_studio_command(vcvars):
    # cmd /s /c removes the outer quotes. Pass its command line unchanged:
    # subprocess's argv-list quoting would turn the inner quotes into \".
    return f'cmd.exe /d /s /c "call "{vcvars}" >nul && set"'


def initialize_visual_studio(environment):
    if os.name != 'nt' or environment.get('VSCMD_ARG_TGT_ARCH') == 'x64':
        return environment
    vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    if not vswhere.is_file():
        raise ValueError('Install Visual Studio Build Tools with Desktop development with C++ first')
    installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
        '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
    vcvars = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
    if not vcvars.is_file() or any(char in str(vcvars) for char in '"\r\n&|<>^%!'):
        raise ValueError('Visual Studio x64 tools could not be located')
    # The only shell text is this fixed toolchain bootstrap, never user settings.
    output = subprocess.check_output(visual_studio_command(vcvars),
                                     text=True, env=environment)
    result = environment.copy()
    for line in output.splitlines():
        key, separator, value = line.partition('=')
        if separator and key:
            result[key] = value
    return result


def export_worker(source, name, kickoff):
    """Use the existing checked RLBot exporter with a private actor container."""
    import torch
    from slater_mechanics_eval import load_actor
    from slater_model_selection import weights_from_source
    from export_rlbot_v4 import export, OUTPUT
    validate_settings({'export_name': name, 'export_kickoff': kickoff})
    source = source_file(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    # Native CUDA archives can retain CUDA device constants in their graph.
    # Transfer weights to the verified CPU template instead of executing that
    # archive's graph; both kickoff variants then get the same portable actor.
    actor = load_actor(ROOT, ROOT / 'vendor/nexto/nexto-model.pt').eval()
    weights = weights_from_source(source)
    if any(not torch.is_tensor(value) or not torch.isfinite(value).all() for value in weights.values()):
        raise ValueError('Attention source contains nonfinite or non-tensor weights')
    actor.load_state_dict(weights, strict=True)
    modes = ('learned', 'scripted') if kickoff == 'both' else (kickoff,)
    names = {mode: name + ('_Scripted' if mode == 'scripted' else '_Learned') for mode in modes}
    for export_name in names.values():
        if (OUTPUT / export_name).exists():
            raise FileExistsError('Export exists; choose a new export name: ' + export_name)
    folder = BASE / 'exports' / f'{name}_{time.time_ns()}'
    folder.mkdir(parents=True, exist_ok=False)
    checkpoint = folder / 'attention.pt'
    torch.save({'actor': actor.state_dict(), 'source': str(source)}, checkpoint)
    for mode, export_name in names.items():
        export(checkpoint, export_name, scripted_kickoff=mode == 'scripted')
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Source checkpoint changed during export')
    print('STUDIO_EXPORT_COMPLETE', json.dumps({'exports': {mode: str(OUTPUT / value) for mode, value in names.items()},
                                              'source_unchanged': True}), flush=True)


class TrainingStudio:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        self.tk, self.ttk, self.messagebox, self.filedialog = tk, ttk, messagebox, filedialog
        self.window = tk.Tk()
        self.window.title('Rocket League Training Studio')
        screen_width, screen_height = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        width, height = min(1100, screen_width - 40), min(850, screen_height - 90)
        self.window.geometry(f'{max(800, width)}x{max(580, height)}')
        self.window.minsize(min(920, screen_width - 40), min(580, screen_height - 90))
        self.manager = ProcessManager()
        self.settings = validate_settings(read_json(BASE / 'settings.json', default_settings()))
        self.forms = {}
        self.buttons = []
        self.events = []
        self.event_lock = threading.Lock()
        self.log_offset = 0
        self.log_remainder = ''
        self.last_finished_pid = None
        self.tab_canvases = []
        self.status_var = tk.StringVar(value='Ready — choose a protected starting model or a saved selection.')
        self.summary_var = tk.StringVar(value='No model is promoted from a training reward or KL value.')
        self._layout()
        self._load_forms()
        self.refresh_results()
        if self.manager.active:
            self.status_var.set('Reconnected to running job — ' + self.manager.job['run'])
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.after(250, self.poll)

    def _layout(self):
        tk, ttk = self.tk, self.ttk
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Rocket League Training Studio', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Keep every model. Compare fairly. Continue from evidence.', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 8))
        common = ttk.LabelFrame(outer, text='Starting model', padding=8)
        common.pack(fill='x')
        self._entry(common, 'source', 'Model', 0, width=75)
        ttk.Button(common, text='Browse file', command=self.browse_source).grid(row=0, column=2, padx=3)
        ttk.Button(common, text='Saved models', command=self.model_browser).grid(row=0, column=3, padx=3)
        self._entry(common, 'selection', 'Selection JSON', 1, width=75)
        ttk.Button(common, text='Browse selection', command=self.browse_selection).grid(row=1, column=2, columnspan=2, padx=3)
        ttk.Label(common, text='Selection JSON takes precedence for new training. Clear it to use the chosen model.').grid(row=2, column=1, columnspan=3, sticky='w')
        common.columnconfigure(1, weight=1)
        notebook = ttk.Notebook(outer)
        self.notebook = notebook
        notebook.pack(fill='both', expand=True, pady=10)
        train, selection, campaign, replay, results, advanced = [self._scrollable_tab(notebook, label)
            for label in ('Training', 'Find best models', 'Auto campaign', 'Replay tools', 'Results', 'All settings')]
        self.window.bind_all('<MouseWheel>', self._tab_wheel, add='+')
        self.window.bind_all('<Button-4>', self._tab_wheel, add='+')
        self.window.bind_all('<Button-5>', self._tab_wheel, add='+')
        self._entry(train, 'native_run', 'Run name', 0)
        self._entry(train, 'updates', 'Additional updates', 1)
        self._entry(train, 'profile.device', 'Device', 2, choices=('auto', 'cpu', 'cuda'))
        self._entry(train, 'profile.routine', 'Routine', 3, choices=ROUTINES)
        self._entry(train, 'profile.formats', 'Team formats', 4)
        presets = ttk.Frame(train); presets.grid(row=4, column=2, padx=8)
        ttk.Button(presets, text='Balanced teams', command=lambda: self.set_formats(False)).pack(side='left', padx=2)
        ttk.Button(presets, text='All nine formats', command=lambda: self.set_formats(True)).pack(side='left', padx=2)
        self._entry(train, 'profile.games', 'Parallel worlds', 5)
        self._entry(train, 'profile.steps', 'Steps per world', 6)
        self._entry(train, 'profile.actor_lr', 'Actor learning rate', 7)
        self._entry(train, 'profile.critic_lr', 'Critic learning rate', 8)
        self._entry(train, 'profile.target_kl', 'PPO KL limit', 9)
        self._entry(train, 'profile.teacher_weight', 'Teacher anchor', 10)
        self._entry(train, 'profile.selfplay_refresh', 'Self-play refresh interval', 11)
        row = ttk.Frame(train); row.grid(row=12, column=0, columnspan=3, sticky='w', pady=8)
        for label, action in (('Build engine', 'build'), ('Parity check', 'parity'), ('Smoke test', 'smoke'), ('Start new run', 'train'), ('Resume', 'resume')):
            self._job_button(row, label, 'native', action)
        ttk.Label(train, text='A new run preserves its source. Resume restores the saved profile and adds the requested updates.').grid(row=13, column=0, columnspan=3, sticky='w')
        self._entry(selection, 'selector_run', 'Selection run', 0)
        self._entry(selection, 'max_games', 'Game budget this launch', 1)
        self._entry(selection, 'until', 'Stop after stage', 2, choices=('screen', 'refine', 'finalists', 'confirm'))
        ttk.Label(selection, text='Discover mechanics updates and accepted models, team updates and native attention checkpoints.\nIdentical actors are compared once. Reference models and all original files are preserved.\nScreen first, then resume with a larger budget or later stage.').grid(row=3, column=0, columnspan=3, sticky='w', pady=12)
        row = ttk.Frame(selection); row.grid(row=4, column=0, columnspan=3, sticky='w')
        for label, action in (('Inventory models', 'inventory'), ('Start comparison', 'run'), ('Resume comparison', 'resume'), ('Rebuild ranking', 'rank')):
            self._job_button(row, label, 'selector', action)
        ttk.Button(selection, text='Use this selection for training', command=self.use_selection).grid(row=5, column=0, columnspan=3, sticky='w', pady=12)
        ttk.Label(selection, text='Change checkpoint families, rivals, seeds, duration and shortlist limits in All settings → selector.').grid(row=6, column=0, columnspan=3, sticky='w')
        self._entry(campaign, 'campaign_run', 'Campaign name', 0)
        self._entry(campaign, 'campaign.cycles', 'Cycles (0 = time/unlimited budget)', 1)
        self._entry(campaign, 'campaign.branch_updates', 'Maximum updates per branch', 2)
        self._entry(campaign, 'campaign.chunk_updates', 'Updates per training chunk', 3)
        self._entry(campaign, 'campaign.screen_every', 'Screen checkpoint interval', 4)
        self._entry(campaign, 'campaign.plateau_chunks', 'Stalled chunks before rotating', 5)
        self._entry(campaign, 'campaign.max_minutes', 'Time limit in minutes (0 = none)', 6)
        self._entry(campaign, 'campaign.unlimited_until_paused', 'Allow unlimited when cycles = 0', 7, choices=('False', 'True'))
        ttk.Label(campaign, text='The campaign branches from a protected champion, trains in finite chunks and compares\nagainst its parent. A failed or stalled branch keeps its checkpoints and rotates to another routine.\nConfirmation uses fresh seeds. A weak branch cannot replace the protected playing model.').grid(row=8, column=0, columnspan=3, sticky='w', pady=12)
        row = ttk.Frame(campaign); row.grid(row=9, column=0, columnspan=3, sticky='w')
        self._job_button(row, 'Start auto campaign', 'campaign', 'run')
        self._job_button(row, 'Resume campaign', 'campaign', 'resume')
        ttk.Label(campaign, text='Adjust promotion limits, routine order, self-play, per-routine parameters\nand evaluation settings in All settings → campaign.').grid(row=10, column=0, columnspan=3, sticky='w', pady=12)
        ttk.Button(campaign, text='Load full campaign defaults into editor', command=self.load_campaign_defaults).grid(row=11, column=0, columnspan=3, sticky='w')
        ttk.Label(replay, text='Prepare or inspect existing replay data. Native attention training currently uses\nRocketSim PPO; these tools do not add human replay gradients to that trainer.').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 10))
        self._entry(replay, 'replays.inputs', 'Replay folder', 1, width=65)
        ttk.Button(replay, text='Browse', command=lambda: self.browse_replay_folder('inputs')).grid(row=1, column=2)
        self._entry(replay, 'replays.output', 'Prepared dataset folder', 2, width=65)
        self._entry(replay, 'replays.max_replays', 'Maximum replays', 3)
        self._entry(replay, 'replays.workers', 'Parser workers', 4)
        row = ttk.Frame(replay); row.grid(row=5, column=0, columnspan=3, sticky='w', pady=8)
        self._job_button(row, 'Prepare replay dataset', 'replay', 'prepare')
        ttk.Label(replay, text='Input audit below is for the earlier native MLP event bank and its .lt checkpoint.\nIt distinguishes recorded controls from inferred labels; it is not an attention-model evaluation.').grid(row=6, column=0, columnspan=3, sticky='w', pady=8)
        self._entry(replay, 'replays.prepared', 'Legacy prepared event folder', 7, width=65)
        ttk.Button(replay, text='Browse', command=lambda: self.browse_replay_folder('prepared')).grid(row=7, column=2)
        self._entry(replay, 'replays.audit_checkpoint', 'Legacy native checkpoint folder', 8, width=65)
        ttk.Button(replay, text='Browse', command=lambda: self.browse_replay_folder('audit_checkpoint')).grid(row=8, column=2)
        self._entry(replay, 'replays.raw_count', 'Raw input samples to inspect', 9)
        row = ttk.Frame(replay); row.grid(row=10, column=0, columnspan=3, sticky='w', pady=8)
        self._job_button(row, 'Audit legacy replay inputs', 'replay', 'audit')
        ttk.Label(replay, text='These preparation/audit tools finish their finite budget and have no safe pause command.\nLeave them running until completion; cached preparation shards are preserved.').grid(row=11, column=0, columnspan=3, sticky='w')
        self._entry(results, 'checkpoint', 'Native checkpoint folder', 0, width=65)
        ttk.Button(results, text='Choose folder', command=self.browse_checkpoint).grid(row=0, column=2)
        self._entry(results, 'eval_seeds', 'Independent evaluation seeds', 1)
        self._entry(results, 'eval_seconds', 'Seconds per game', 2)
        row = ttk.Frame(results); row.grid(row=3, column=0, columnspan=3, sticky='w', pady=8)
        self._job_button(row, 'Evaluate checkpoint', 'native', 'eval')
        self._job_button(row, 'Export attention .pt', 'native', 'export')
        self._entry(results, 'export_name', 'RLBot export name', 4)
        self._entry(results, 'export_kickoff', 'Export kickoff', 5, choices=('both', 'learned', 'scripted'))
        row = ttk.Frame(results); row.grid(row=6, column=0, columnspan=3, sticky='w', pady=8)
        self._job_button(row, 'Export chosen model to RLBot', 'export', 'export')
        self.ttk.Button(row, text='Choose campaign champion', command=self.use_campaign_champion).pack(side='left', padx=3)
        ttk.Button(row, text='Refresh reports', command=self.refresh_results).pack(side='left', padx=3)
        ttk.Button(row, text='Open results folder', command=self.open_results).pack(side='left', padx=3)
        self.report = tk.Text(results, height=14, wrap='word', font=('Consolas', 9))
        self.report.grid(row=7, column=0, columnspan=3, sticky='nsew')
        results.rowconfigure(7, weight=1); results.columnconfigure(1, weight=1)
        ttk.Label(advanced, text='Every supported parameter can be edited below. Click Apply JSON before starting a job.\nConfigurations contain paths and settings; credentials are rejected. Backend validation also applies.').pack(anchor='w')
        self.editor = tk.Text(advanced, wrap='none', font=('Consolas', 10))
        row = ttk.Frame(advanced); row.pack(fill='x')
        for text, fn in (('Apply JSON', self.apply_editor), ('Import settings', self.import_settings), ('Export settings', self.export_settings), ('Load selector defaults', self.load_selector_defaults)):
            ttk.Button(row, text=text, command=fn).pack(side='left', padx=3)
        self.editor.pack(fill='both', expand=True, pady=8)
        controls = ttk.Frame(outer); controls.pack(fill='x')
        self.pause_button = ttk.Button(controls, text='Pause active job safely', command=self.pause_job)
        self.pause_button.pack(side='left')
        ttk.Label(controls, textvariable=self.status_var).pack(side='left', padx=10)
        ttk.Label(outer, textvariable=self.summary_var).pack(anchor='w', pady=(5, 2))
        self.log = tk.Text(outer, height=8, wrap='word', font=('Consolas', 9), state='disabled')
        self.log.pack(fill='x')

    def _scrollable_tab(self, notebook, label):
        page = self.ttk.Frame(notebook)
        notebook.add(page, text=label)
        canvas = self.tk.Canvas(page, borderwidth=0, highlightthickness=0)
        scroll = self.ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        content = self.ttk.Frame(canvas, padding=10)
        item = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        self.tab_canvases.append(canvas)
        return content

    def _tab_wheel(self, event):
        # Text and combobox widgets keep their normal scrolling behavior.
        if event.widget.winfo_class() in ('Text', 'TCombobox'):
            return
        try:
            canvas = self.tab_canvases[self.notebook.index(self.notebook.select())]
            direction = -1 if getattr(event, 'num', None) == 4 else 1 if getattr(event, 'num', None) == 5 else -int(event.delta / 120)
            if direction:
                canvas.yview_scroll(direction, 'units')
        except (self.tk.TclError, IndexError):
            pass

    def _entry(self, frame, key, label, row, width=26, choices=None):
        ttk = self.ttk
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=3)
        variable = self.tk.StringVar()
        self.forms[key] = variable
        widget = ttk.Combobox(frame, textvariable=variable, values=choices, state='readonly', width=width) if choices else ttk.Entry(frame, textvariable=variable, width=width)
        widget.grid(row=row, column=1, sticky='ew', pady=3)

    def _job_button(self, frame, label, engine, action):
        button = self.ttk.Button(frame, text=label, command=lambda: self.start_job(engine, action))
        button.pack(side='left', padx=3)
        self.buttons.append(button)

    def _load_forms(self):
        for key, variable in self.forms.items():
            if key.startswith('profile.'):
                value = self.settings['native_profile'].get(key.removeprefix('profile.'), '')
            elif key.startswith('replays.'):
                value = self.settings['replays'][key.removeprefix('replays.')]
            elif key.startswith('campaign.'):
                value = self.settings['campaign'][key.removeprefix('campaign.')]
            else:
                value = self.settings[key]
            variable.set(str(value))
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', json.dumps(self.settings, indent=2))

    def gather(self):
        settings = deepcopy(self.settings)
        for key, variable in self.forms.items():
            value = variable.get().strip()
            if key.startswith('profile.'):
                target, field = settings['native_profile'], key.removeprefix('profile.')
            elif key.startswith('replays.'):
                target, field = settings['replays'], key.removeprefix('replays.')
            elif key.startswith('campaign.'):
                target, field = settings['campaign'], key.removeprefix('campaign.')
            else:
                target, field = settings, key
            existing = target.get(field, '')
            if type(existing) is bool:
                if value not in ('True', 'False'):
                    raise ValueError(field + ' must be True or False')
                value = value == 'True'
            elif type(existing) is int:
                value = int(value)
            elif type(existing) is float:
                value = float(value)
            target[field] = value
        settings = validate_settings(settings)
        atomic_json(BASE / 'settings.json', settings)
        self.settings = settings
        return settings

    def show_error(self, exc):
        self.messagebox.showerror('Training Studio', str(exc), parent=self.window)

    def apply_editor(self):
        try:
            self.settings = validate_settings(json.loads(self.editor.get('1.0', 'end')))
            atomic_json(BASE / 'settings.json', self.settings)
            self._load_forms()
            self.status_var.set('Settings applied.')
        except Exception as exc:
            self.show_error(exc)

    def import_settings(self):
        path = self.filedialog.askopenfilename(filetypes=[('JSON settings', '*.json')])
        if path:
            try:
                self.settings = validate_settings(json.loads(Path(path).read_text(encoding='utf-8')))
                atomic_json(BASE / 'settings.json', self.settings); self._load_forms()
            except Exception as exc:
                self.show_error(exc)

    def export_settings(self):
        try:
            settings = self.gather()
            path = self.filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON settings', '*.json')])
            if path:
                atomic_json(path, settings)
        except Exception as exc:
            self.show_error(exc)

    def load_selector_defaults(self):
        self._load_defaults('selector')

    def load_campaign_defaults(self):
        self._load_defaults('campaign')

    def _load_defaults(self, engine):
        try:
            self.settings = self.gather()
            def load():
                try:
                    if engine == 'selector':
                        from slater_model_selection import DEFAULT
                        value = deepcopy(DEFAULT)
                    else:
                        from slater_champion_campaign import default_config
                        value = default_config()
                    self.emit('defaults', (engine, value))
                except Exception as exc:
                    self.emit('error', str(exc))
            threading.Thread(target=load, daemon=True).start()
            self.status_var.set('Loading adjustable defaults…')
        except Exception as exc:
            self.show_error(exc)

    def browse_source(self):
        path = self.filedialog.askopenfilename(initialdir=ROOT / 'data/isolated', filetypes=[('Attention checkpoints', '*.pt')])
        if path:
            self.forms['source'].set(path); self.forms['selection'].set('')

    def browse_selection(self):
        path = self.filedialog.askopenfilename(initialdir=ROOT / 'data/isolated/model_selection', filetypes=[('Selection JSON', '*.json')])
        if path:
            self.forms['selection'].set(path)

    def browse_checkpoint(self):
        path = self.filedialog.askdirectory(initialdir=ROOT / 'data/isolated/native_attention/runs')
        if path:
            self.forms['checkpoint'].set(path)

    def browse_replay_folder(self, key):
        path = self.filedialog.askdirectory(initialdir=ROOT / 'data')
        if path:
            self.forms['replays.' + key].set(path)

    def set_formats(self, all_nine):
        try:
            self.settings = format_preset(self.gather(), all_nine)
            self._load_forms()
            self.status_var.set('Team formats updated for new training and new campaigns.')
        except Exception as exc:
            self.show_error(exc)

    def model_browser(self):
        popup = self.tk.Toplevel(self.window); popup.title('Saved models'); popup.geometry('950x550')
        filter_var = self.tk.StringVar()
        self.ttk.Label(popup, text='Choose a starting model. Original files remain protected. Filter by family, filename or path.').pack(anchor='w', padx=10, pady=8)
        self.ttk.Entry(popup, textvariable=filter_var).pack(fill='x', padx=10)
        tree = self.ttk.Treeview(popup, columns=('family', 'name', 'path'), show='headings')
        for column, width in (('family', 90), ('name', 190), ('path', 600)):
            tree.heading(column, text=column.title()); tree.column(column, width=width)
        tree.pack(fill='both', expand=True, padx=10, pady=8)
        entries = discover_checkpoints()
        def fill(*unused):
            tree.delete(*tree.get_children())
            needle = filter_var.get().lower()
            for item in entries:
                if needle in (' '.join(str(value) for value in item.values())).lower():
                    tree.insert('', 'end', values=(item['family'], item['name'], item['path']))
        def choose(*unused):
            selected = tree.selection()
            if selected:
                self.forms['source'].set(tree.item(selected[0], 'values')[2]); self.forms['selection'].set(''); popup.destroy()
        filter_var.trace_add('write', fill); tree.bind('<Double-1>', choose)
        self.ttk.Button(popup, text='Use selected model', command=choose).pack(pady=8)
        fill()

    def use_selection(self):
        try:
            folder = result_directory('selector', self.forms['selector_run'].get())
            path = folder / 'selection.json'
            selection = read_json(path)
            if not selection or not selection.get('stage_complete'):
                raise ValueError('Complete the current selection stage before using its source')
            self.forms['selection'].set(str(path))
            self.status_var.set('Selection chosen for a new isolated training experiment.')
        except Exception as exc:
            self.show_error(exc)

    def use_campaign_champion(self):
        try:
            cfg = self.gather()
            self.forms['source'].set(str(campaign_champion(cfg)))
            self.forms['selection'].set('')
            self.status_var.set('Campaign champion selected for export or a new isolated run.')
        except Exception as exc:
            self.show_error(exc)

    def start_job(self, engine, action):
        try:
            cfg = self.gather()
            if engine == 'native' and action in ('parity', 'smoke'):
                # Diagnostics must not consume the user's intended training name.
                cfg['native_run'] = 'studio_' + action + '_' + str(time.time_ns())
            if engine == 'selector' and action == 'run' and (result_directory(engine, cfg['selector_run']) / 'config.json').is_file():
                action = 'resume'
            config_file = None
            if engine in ('selector', 'campaign') and action in ('inventory', 'run'):
                options = job_config(engine, cfg)
                config_file = BASE / 'configs' / f'{engine}_{time.time_ns()}.json'
                atomic_json(config_file, options)
            command = command_for(engine, action, cfg, config_file=config_file)
            run = cfg['replays']['audit_run'] if engine == 'replay' else cfg.get({'native': 'native_run', 'selector': 'selector_run', 'campaign': 'campaign_run'}.get(engine, 'export_name'))
            job = self.manager.start(command, engine, action, run)
            self.last_finished_pid = None; self.log_offset = 0; self.log_remainder = ''
            self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.log.configure(state='disabled')
            self.status_var.set(f'{action.replace("_", " ").title()} running — {run}')
            self.summary_var.set('Log: ' + job['log'])
        except Exception as exc:
            self.show_error(exc)

    def pause_job(self):
        try:
            if not self.manager.active:
                raise ValueError('No active Studio job')
            job = self.manager.job
            cfg = deepcopy(self.settings)
            key = {'native': 'native_run', 'selector': 'selector_run', 'campaign': 'campaign_run'}.get(job['engine'])
            if key is None:
                raise ValueError('This finite utility has no pause boundary; let it finish')
            cfg[key] = job['run']
            command = command_for(job['engine'], 'pause', cfg)
            def pause():
                try:
                    message = self.manager.request_pause(command)
                    self.emit('status', message or 'Pause requested; waiting for a safe checkpoint.')
                except Exception as exc:
                    self.emit('error', str(exc))
            threading.Thread(target=pause, daemon=True).start()
            self.status_var.set('Pause requested — wait for the active job to finish.')
        except Exception as exc:
            self.show_error(exc)

    def emit(self, kind, payload):
        with self.event_lock:
            self.events.append((kind, payload))

    def poll(self):
        with self.event_lock:
            events, self.events = self.events, []
        for kind, payload in events:
            if kind == 'error':
                self.show_error(payload)
            elif kind == 'defaults':
                engine, value = payload
                self.settings[engine] = value; self._load_forms()
                self.status_var.set('Defaults loaded into All settings; edit and apply before starting.')
            else:
                self.status_var.set(payload)
        job = self.manager.job
        if job:
            try:
                with Path(job['log']).open('rb') as stream:
                    stream.seek(self.log_offset); content = stream.read(128 * 1024); self.log_offset = stream.tell()
                if content:
                    text = content.decode('utf-8', errors='replace')
                    self.log.configure(state='normal'); self.log.insert('end', text)
                    if int(self.log.index('end-1c').split('.')[0]) > 1200:
                        self.log.delete('1.0', '400.0')
                    self.log.see('end'); self.log.configure(state='disabled')
                    lines = (self.log_remainder + text).split('\n'); self.log_remainder = lines.pop()
                    for line in lines:
                        progress = progress_from_line(line)
                        if progress:
                            keep = {key: value for key, value in progress.items() if key in
                                    ('update', 'updates', 'decisions', 'status', 'phase', 'routine', 'champion', 'promotions', 'actor_loss', 'teacher_kl')}
                            ppo = progress.get('ppo', {})
                            if isinstance(ppo, dict):
                                keep.update({key: ppo[key] for key in ('actor_loss', 'teacher_kl', 'rollout_policy_kl') if key in ppo})
                            self.summary_var.set(json.dumps(keep, ensure_ascii=False)[:230])
            except OSError:
                pass
            if not self.manager.active and self.last_finished_pid != job['pid']:
                self.last_finished_pid = job['pid']; code = self.manager.process.returncode
                self.status_var.set('Finished successfully.' if code == 0 else f'Job stopped with error {code}. Read the log below.')
                self.refresh_results()
        for button in self.buttons:
            button.configure(state='disabled' if self.manager.active else 'normal')
        self.pause_button.configure(state='normal' if self.manager.active else 'disabled')
        self.window.after(250, self.poll)

    def refresh_results(self):
        try:
            cfg = self.gather()
            output = []
            for engine, key in (('native', 'native_run'), ('selector', 'selector_run'), ('campaign', 'campaign_run')):
                folder = result_directory(engine, cfg[key])
                output += [engine.title() + ': ' + cfg[key], str(folder)]
                for filename in ('progress.json', 'selected.json', 'selection.json'):
                    payload = read_json(folder / filename)
                    if payload:
                        concise = {key: value for key, value in payload.items() if key in
                                   ('status', 'phase', 'stage', 'stage_complete', 'updates', 'decisions', 'champion', 'checkpoint', 'promotions', 'routine', 'branch_run', 'playing_model', 'confirmed_best', 'completed_games', 'total_games')}
                        output.append(json.dumps(concise or payload, indent=2, ensure_ascii=False)[:6000])
                shortlist = folder / 'SHORTLIST.md'
                if shortlist.is_file():
                    output.append(shortlist.read_text(encoding='utf-8')[:12000])
                evaluations = sorted((folder / 'evaluations').glob('*/comparison.json'))
                if evaluations:
                    output.append('Latest matched evaluation: ' + str(evaluations[-1]))
                    output.append(json.dumps(read_json(evaluations[-1]), indent=2)[:4000])
                output.append('')
            self.report.delete('1.0', 'end'); self.report.insert('1.0', '\n'.join(output))
        except Exception as exc:
            self.show_error(exc)

    def open_results(self):
        try:
            BASE.parent.mkdir(parents=True, exist_ok=True)
            if os.name == 'nt':
                os.startfile(str(BASE.parent))
            else:
                subprocess.Popen(['xdg-open', str(BASE.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self.show_error(exc)

    def close(self):
        if self.manager.active:
            answer = self.messagebox.askyesnocancel('Job still running',
                'Leave the job running in the background?\n\nYes: close the window and keep running.\nNo: request a safe pause and keep this window open.\nCancel: keep working.', parent=self.window)
            if answer is None:
                return
            if not answer:
                self.pause_job(); return
        try:
            self.gather()
        except Exception as exc:
            self.show_error(exc); return
        self.window.destroy()

    def mainloop(self):
        self.window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    workers = parser.add_mutually_exclusive_group()
    workers.add_argument('--worker-build', action='store_true')
    workers.add_argument('--worker-export', action='store_true')
    workers.add_argument('--worker-job', type=Path)
    parser.add_argument('--source')
    parser.add_argument('--build-dir')
    parser.add_argument('--export-name', default='StudioChampion01')
    parser.add_argument('--export-kickoff', choices=('both', 'learned', 'scripted'), default='both')
    args = parser.parse_args()
    if args.worker_job:
        specification = read_json(args.worker_job)
        result = Path(specification['result'])
        try:
            command = specification['argv']
            if not isinstance(command, list) or any(not isinstance(arg, str) for arg in command):
                raise ValueError('Invalid worker arguments')
            code = subprocess.call(command, cwd=specification['root'])
        except Exception:
            traceback.print_exc(); code = 1
        atomic_json(result, {'returncode': code, 'completed_at': datetime.now(timezone.utc).isoformat()})
        print('STUDIO_JOB_COMPLETE', json.dumps({'returncode': code}), flush=True)
        raise SystemExit(code)
    elif args.worker_build:
        environment = initialize_visual_studio(os.environ.copy())
        command = [child_python(), str(ROOT / 'slater_native_attention.py'), 'build']
        if args.build_dir:
            command += ['--build-dir', args.build_dir]
        subprocess.run(command, check=True, cwd=ROOT, env=environment)
    elif args.worker_export:
        export_worker(args.source, args.export_name, args.export_kickoff)
    else:
        try:
            TrainingStudio().mainloop()
        except Exception as exc:
            logfile = BASE / 'startup_errors.log'
            logfile.parent.mkdir(parents=True, exist_ok=True)
            with logfile.open('a', encoding='utf-8') as output:
                traceback.print_exc(file=output)
            try:
                from tkinter import Tk, messagebox
                window = Tk(); window.withdraw()
                messagebox.showerror('Training Studio could not start', f'{exc}\n\nDetails: {logfile}', parent=window)
                window.destroy()
            except Exception:
                if sys.stderr is not None:
                    print(f'Training Studio failed: {exc}; details: {logfile}', file=sys.stderr)
            raise


if __name__ == '__main__':
    main()
