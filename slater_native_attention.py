"""Isolated native continuation of the original attention actor.

This launcher never silently substitutes Nexto for a missing update180 and never
changes existing native runs. Native results are experiments, not promotions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import torch

from GigaLearn_Project.Native_Backend import native_setup as helper
from slater_mechanics_eval import load_actor
from slater_v041_core import atomic_json, process_lock, read_json, sha256

ROOT = Path(__file__).resolve().parent
HERE = ROOT / 'GigaLearn_Project/Native_Attention'
BASE = ROOT / 'data/isolated/native_attention'
DEFAULT_SOURCE = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
DEFAULT_RIVAL = ROOT / 'vendor/nexto/nexto-model.pt'
CHECKPOINT_FILES = ('actor.pt', 'teacher.pt', 'critic.pt', 'actor_optimizer.pt',
                    'critic_optimizer.pt', 'rng.pt', 'protocol.json', 'state.json')
PROFILE = {'games': 8, 'steps': 128, 'device': 'auto', 'seed': 20261013,
           'actor_lr': 3e-6, 'critic_lr': 1e-4, 'target_kl': .005,
           'teacher_weight': .1, 'seconds': 12., 'eval_seeds': 2}


def run_path(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ValueError('Use an ASCII run name with letters, numbers, underscore or hyphen')
    return BASE / 'runs' / name


def validate_profile(profile):
    for key, low, high in (('games', 1, 128), ('steps', 16, 4096), ('seed', 1, 2**31-1),
                           ('eval_seeds', 1, 64)):
        value = profile[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Invalid {key}: expected integer {low}..{high}')
    for key, low, high in (('actor_lr', 1e-8, 5e-5), ('critic_lr', 1e-7, .001),
                           ('target_kl', .0001, .05), ('teacher_weight', 0., 1.),
                           ('seconds', 3., 300.)):
        value = profile[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Invalid {key}')
    if profile['device'] not in ('cpu', 'cuda', 'auto'):
        raise ValueError('Device must be cpu, cuda or auto')
    return dict(profile)


def validate_source(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Original attention checkpoint missing: {path}. '
                                'Supply --source explicitly; there is no automatic Nexto fallback.')
    return path


def export_actor(source, destination):
    """Private TorchScript export with an exact parameter comparison."""
    source = validate_source(source)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'Private export already exists: {destination}')
    before = sha256(source)
    actor = load_actor(ROOT, source, trainable=True).eval()
    if len(list(actor.parameters())) != 44 or sum(p.numel() for p in actor.parameters()) != 444032:
        raise ValueError('Only the original Nexto attention actor is supported')
    destination.parent.mkdir(parents=True, exist_ok=True)
    torch.jit.save(actor, str(destination))
    portable = torch.jit.load(str(destination), map_location='cpu').eval()
    original, exported = actor.state_dict(), portable.state_dict()
    if original.keys() != exported.keys() or not all(torch.equal(v, exported[k]) for k, v in original.items()):
        destination.unlink()
        raise ValueError('Private export changed attention weights')
    if sha256(source) != before:
        destination.unlink()
        raise RuntimeError('Source changed during export; stop the writer and use a complete checkpoint')
    return {'path': str(source), 'sha256': before, 'exported_sha256': sha256(destination),
            'actor_weights_identical': True, 'actor_tensors': 44, 'actor_parameters': 444032}


def verify_giga_source(source):
    """Verify a pinned original or complete known patch, without editing it."""
    source = Path(source).resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != helper.GIGA:
        raise ValueError('Native attention requires the pinned GigaLearn source commit')
    manifest = read_json(helper.HERE / 'patch_manifest.json')
    possible = {'original', 'patched', 'legacy', 'metrics_base', 'curriculum_base'}
    for name, variants in manifest.items():
        digest = hashlib.sha256((source / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        possible &= {key for key, value in variants.items() if value == digest}
    if not possible:
        raise ValueError('GigaLearn source has unrecognized edits or a partial patch; '
                         'use an intact pinned source folder. Existing files were not changed.')
    return source


def source_checkout(explicit=None):
    if explicit is not None:
        return verify_giga_source(explicit)
    existing = helper.BASE / 'source'
    if existing.is_dir():
        return verify_giga_source(existing)
    isolated = BASE / 'source'
    helper.fetch('https://github.com/ZealanL/GigaLearnCPP-Leak.git', isolated, helper.GIGA)
    helper.patch_source(isolated)
    return verify_giga_source(isolated)


def build(build_dir=None, giga_source=None, jobs=1):
    if type(jobs) is not int or not 1 <= jobs <= 4:
        raise ValueError('Use 1..4 compiler jobs (1 recommended for limited RAM)')
    if os.name == 'nt' and not shutil.which('cl'):
        raise ValueError('Run ATTENTION_NATIVE.bat build to initialize Visual Studio x64 tools')
    source = source_checkout(giga_source)
    folder = Path(build_dir or BASE / 'build').resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cuda_args, environment = helper.cuda_configuration(torch)
    python_library, python_include = helper.python_paths()
    configure = [helper.tool('cmake'), '-S', str(HERE), '-B', str(folder), '-G', 'Ninja',
                 '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_MAKE_PROGRAM={helper.tool("ninja")}',
                 f'-DGIGALEARN_SOURCE={source}', f'-DCMAKE_PREFIX_PATH={torch.utils.cmake_prefix_path}',
                 f'-DPython_EXECUTABLE={sys.executable}', f'-DPYTHON_EXECUTABLE={sys.executable}',
                 f'-DPYTHON_LIBRARY={python_library}', f'-DPYTHON_INCLUDE_DIR={python_include}', *cuda_args]
    for command in (configure, [helper.tool('cmake'), '--build', str(folder), '--target',
                                'SlaterAttentionNative', 'SlaterAttentionObsParity', 'SlaterAttentionPPOParity', '-j', str(jobs)]):
        print('RUN', subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, check=True, env=environment)
    binary = binary_path(folder)
    if not binary.is_file():
        raise RuntimeError('Build did not produce SlaterAttentionNative')
    # The legacy MLP sync helper uses another executable name. Copy only this
    # separate build's own DLL; never repair/replace the old native build.
    if os.name == 'nt':
        library = folder / 'giga/GigaLearnCPP.dll'
        if library.is_file():
            shadow = folder / library.name
            temporary = folder / ('.' + library.name + '.attention-tmp')
            shutil.copyfile(library, temporary)
            if sha256(temporary) != sha256(library):
                temporary.unlink(missing_ok=True)
                raise RuntimeError('Native library changed during private build copy')
            os.replace(temporary, shadow)
    stamp = folder / 'build_identity.json'
    if stamp.exists():
        old_stamp = read_json(stamp)
        atomic_json(stamp, {**old_stamp, 'backend_sha': backend_identity()})
    identity = binary_identity(folder)
    atomic_json(folder / 'build_identity.json', {**identity, 'gigalearn_commit': helper.GIGA,
                'source': str(source), 'code': code_identity(), 'backend_sha': backend_identity()})
    print('SLATER_ATTENTION_BUILD', json.dumps(identity), flush=True)
    return binary


def binary_path(folder=None):
    return Path(folder or BASE / 'build').resolve() / ('SlaterAttentionNative.exe' if os.name == 'nt' else 'SlaterAttentionNative')


def backend_identity():
    names = sorted([p for p in HERE.glob('*') if p.suffix in ('.h','.cpp') or p.name == 'CMakeLists.txt'])
    return {p.name: sha256(p) for p in names}


def binary_identity(folder=None):
    binary = binary_path(folder)
    if not binary.is_file():
        raise FileNotFoundError('Build native attention first: ATTENTION_NATIVE.bat build')
    identity = {'binary_sha256': sha256(binary)}
    stamp = read_json(binary.parent / 'build_identity.json')
    if stamp and stamp.get('backend_sha') != backend_identity():
        raise ValueError('Native attention source changed since build; run ATTENTION_NATIVE.bat build')
    candidates = (binary.parent / 'giga/GigaLearnCPP.dll', binary.parent / 'giga/libGigaLearnCPP.so')
    for library in candidates:
        if library.is_file():
            shadow = binary.parent / library.name
            if shadow.is_file() and sha256(shadow) != sha256(library):
                raise ValueError('Stale library in isolated attention build; rerun ATTENTION_NATIVE.bat build')
            identity['library_sha256'] = sha256(library)
    return identity


def code_identity():
    names = ['slater_native_attention.py', 'vendor/nexto/nexto_obs.py', 'slater_nexto_scheduler_v038b.py']
    names += [str(path.relative_to(ROOT)).replace('\\', '/') for path in sorted(HERE.glob('*'))
              if path.suffix in ('.cpp', '.h', '.txt')]
    return {name: sha256(ROOT / name) for name in names}


def complete_checkpoint(folder):
    folder = Path(folder).resolve()
    if not re.fullmatch(r'checkpoint_\d{6,}', folder.name):
        raise ValueError('Expected a checkpoint_000001 directory, not one .pt file')
    marker = folder / 'COMPLETE.json'
    if not marker.is_file() and not (folder / 'COMPLETE').is_file():
        raise ValueError(f'Incomplete native attention checkpoint: {folder}')
    missing = [name for name in CHECKPOINT_FILES if not (folder / name).is_file()]
    if missing:
        raise ValueError('Incomplete native checkpoint; missing ' + ', '.join(missing))
    return folder


def latest_checkpoint(run):
    candidates = []
    for folder in (Path(run) / 'checkpoints').glob('checkpoint_*'):
        try:
            complete_checkpoint(folder)
            candidates.append(folder)
        except ValueError:
            continue
    if not candidates:
        raise ValueError('No complete native attention checkpoint is available')
    return max(candidates, key=lambda path: int(path.name.removeprefix('checkpoint_')))


def marker_json(output, marker):
    def finite_payload(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise RuntimeError(f'Nonfinite {marker} measurement')
        if isinstance(value, dict):
            for item in value.values():
                finite_payload(item)
        elif isinstance(value, list):
            for item in value:
                finite_payload(item)
    values = []
    for line in output.splitlines():
        if line.startswith(marker + ' '):
            try:
                value = json.loads(line[len(marker) + 1:])
            except json.JSONDecodeError as exc:
                raise RuntimeError(f'Malformed {marker} marker') from exc
            if not isinstance(value, dict):
                raise RuntimeError(f'{marker} must contain a JSON object')
            finite_payload(value)
            values.append(value)
    if not values:
        raise RuntimeError(f'Native process did not produce {marker}; a zero exit code is insufficient')
    return values[-1]


def checked_process(command, logfile, *, marker, pause=None):
    """Stream output and require an explicit, parsed native completion marker."""
    logfile = Path(logfile)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    env = helper.runtime_environment(command[0], pause or logfile.with_suffix('.pause'))
    print('RUN', subprocess.list2cmdline([str(x) for x in command]), flush=True)
    output = []
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {}
    with logfile.open('w', encoding='utf-8') as handle:
        proc = subprocess.Popen([str(x) for x in command], cwd=Path(command[0]).parent, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding='utf-8', errors='replace', **options)
        try:
            for line in proc.stdout:
                handle.write(line); handle.flush(); print(line, end='', flush=True); output.append(line)
        except KeyboardInterrupt:
            if pause is None:
                raise
            Path(pause).touch()
            print('Pause requested. Waiting for the current update and complete checkpoint.', flush=True)
            for line in proc.stdout:
                handle.write(line); handle.flush(); print(line, end='', flush=True); output.append(line)
        returncode = proc.wait()
    text = ''.join(output)
    if returncode:
        code = f'0x{returncode & 0xffffffff:08X}'
        raise RuntimeError(f'Native attention exited with {returncode} ({code}). Log: {logfile}\n' + text[-3500:])
    return marker_json(text, marker)


def verify_protected(protocol):
    for name in ('source', 'teacher_source', 'rival_source'):
        entry = protocol[name]
        if sha256(entry['path']) != entry['sha256']:
            raise ValueError(f'Protected {name} changed; use a new run after resolving the source')


def native_command(mode, run, profile, *, build_dir=None, checkpoint=None, updates=100, fixture=None, kickoffs=None):
    run = Path(run).resolve()
    args = [binary_path(build_dir), '--mode', mode, '--actor', run / 'initial_actor.pt',
            '--teacher', run / 'teacher.pt', '--rival', run / 'rival.pt',
            '--meshes', helper.meshes(), '--out', run, '--protocol', run / 'protocol.json',
            '--pause', run / 'PAUSE', '--updates', updates]
    for key in ('games', 'steps', 'device', 'seed', 'actor_lr', 'critic_lr',
                'target_kl', 'teacher_weight', 'seconds', 'eval_seeds'):
        args += ['--' + key.replace('_', '-'), profile[key]]
    if checkpoint is not None:
        args += ['--resume', complete_checkpoint(checkpoint)]
    if kickoffs is not None:
        args += ['--kickoffs', Path(kickoffs).resolve()]
    if fixture is not None:
        args += ['--fixture', Path(fixture).resolve()]
    return args


def initialize_run(name, source, teacher=None, rival=None, *, profile=None, build_dir=None):
    run = run_path(name)
    if run.exists():
        raise FileExistsError(f'Run exists: {run}. Use resume or a new --run name.')
    source = validate_source(source)
    teacher = validate_source(teacher or source)
    rival = validate_source(rival or DEFAULT_RIVAL)
    profile = validate_profile(profile or PROFILE)
    if profile['device'] == 'auto':
        profile['device'] = 'cuda' if torch.cuda.is_available() else 'cpu'
    if profile['device'] == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA training requested but this PyTorch runtime cannot use CUDA')
    identity = binary_identity(build_dir)
    run.mkdir(parents=True)
    torch.set_num_threads(1)
    export = export_actor(source, run / 'initial_actor.pt')
    teacher_export = export_actor(teacher, run / 'teacher.pt')
    rival_export = export_actor(rival, run / 'rival.pt')
    protocol = {'version': 1, 'profile': profile, 'source': export,
                'teacher_source': teacher_export, 'rival_source': rival_export,
                'initial_actor_sha256': sha256(run / 'initial_actor.pt'),
                'teacher_sha256': sha256(run / 'teacher.pt'), 'rival_sha256': sha256(run / 'rival.pt'),
                'native': identity, 'code': code_identity(), 'runtime': {'torch': torch.__version__,
                    'python': sys.version.split()[0]}, 'gigalearn_commit': helper.GIGA,
                'learner_scripted_kickoff': False, 'rivals_scripted_kickoff': True,
                'playing_model': str(source), 'human_replay_gradients': False,
                'curriculum': 'normal_match_migration', 'auto_promotion': False}
    atomic_json(run / 'protocol.json', protocol)
    atomic_json(run / 'progress.json', {'status': 'INITIALIZED', 'updates': 0,
                'decisions': 0, 'playing_model': str(source)})
    print('ATTENTION_SOURCE_VERIFIED', json.dumps(export), flush=True)
    return run, protocol


def check_run(name, build_dir=None):
    run = run_path(name)
    protocol = read_json(run / 'protocol.json')
    if not protocol:
        raise ValueError('No saved native attention protocol')
    if protocol['native'] != binary_identity(build_dir) or protocol['code'] != code_identity():
        raise ValueError('Native attention binary or code changed. Preserve this run and choose a new run name.')
    if protocol['runtime'] != {'torch': torch.__version__, 'python': sys.version.split()[0]}:
        raise ValueError('Training runtime changed; use the original environment or a new run')
    for name, key in (('initial_actor.pt', 'initial_actor_sha256'), ('teacher.pt', 'teacher_sha256'),
                      ('rival.pt', 'rival_sha256')):
        if sha256(run / name) != protocol[key]:
            raise ValueError('Protected private actor/teacher/rival changed: ' + name)
    verify_protected(protocol)
    return run, protocol


def train(name, source=DEFAULT_SOURCE, *, teacher=None, rival=None, profile=None,
          build_dir=None, updates=100, resume=False, kickoffs=None):
    if type(updates) is not int or not 1 <= updates <= 100000:
        raise ValueError('Use a bounded 1..100000 additional update budget')
    if resume:
        run, protocol = check_run(name, build_dir)
    else:
        run, protocol = initialize_run(name, source, teacher, rival, profile=profile, build_dir=build_dir)
    with process_lock(run / 'runner.lock'):
        checkpoint = latest_checkpoint(run) if resume else None
        if resume:
            for partial in (run / 'checkpoints').glob('checkpoint_*.partial'):
                preserved = partial.with_name(partial.name + '.interrupted_' + str(time.time_ns()))
                partial.rename(preserved)
                print('Preserved interrupted checkpoint directory:', preserved, flush=True)
        (run / 'PAUSE').unlink(missing_ok=True)
        logfile = run / f'training_{time.time_ns()}.log'
        result = checked_process(native_command('train', run, protocol['profile'], build_dir=build_dir,
                                 checkpoint=checkpoint, updates=updates, kickoffs=kickoffs), logfile,
                                 marker='SLATER_ATTENTION_COMPLETE', pause=run / 'PAUSE')
        saved = latest_checkpoint(run)
        verify_protected(protocol)
        result.update(checkpoint=str(saved), source_unchanged=True, playing_model=protocol['playing_model'],
                      auto_promotion=False, log=str(logfile))
        atomic_json(run / 'session_summary.json', result)
        print('ATTENTION_SESSION', json.dumps(result), flush=True)
        return result


def parity(name, source=DEFAULT_SOURCE, *, build_dir=None, teacher=None, rival=None):
    from slater_attention_native_probe import generate_inputs
    run, protocol = initialize_run(name, source, teacher, rival, build_dir=build_dir)
    actor = torch.jit.load(str(run / 'initial_actor.pt'), map_location='cpu').eval()
    observations = generate_inputs(actor, run, protocol['profile']['seed'])
    result = checked_process(native_command('parity', run, protocol['profile'], build_dir=build_dir,
                             fixture=run / 'team_inputs.pt', updates=1), run / 'parity.log',
                             marker='SLATER_ATTENTION_PARITY')
    verify_protected(protocol)
    # Full parity uses real injected simulator states and a deterministic PPO
    # fixture, not just a forward pass on synthetic tensors.
    import importlib.util
    import numpy as np
    def module_at(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
        return module
    fixtures = module_at('attention_state_fixtures', ROOT / 'tests/native_attention_obs_fixtures.py')
    payload, expected = fixtures.real_states()
    atomic_json(run / 'states.json', payload)
    obs_binary = binary_path(build_dir).parent / ('SlaterAttentionObsParity.exe' if os.name=='nt' else 'SlaterAttentionObsParity')
    subprocess.run([str(obs_binary), str(run/'states.json'), str(run/'native_views.json')], check=True,
                   env=helper.runtime_environment(obs_binary, run/'PAUSE'))
    actual = read_json(run/'native_views.json')['states']; max_error=0.; views=0
    if len(actual) != len(expected): raise ValueError('Observation parity frame count changed')
    for python, frame in zip(expected, actual):
        if [r['agent_id'] for r in frame['observations']] != list(python): raise ValueError('Entity ordering mismatch')
        for row in frame['observations']:
            for key, shape, ref in zip(('q','kv','mask'), ((1,32),(41,24),(41,)), python[row['agent_id']]):
                got=np.asarray(row[key],np.float32).reshape(shape)
                delta=float(np.max(np.abs(got-ref)));max_error=max(max_error,delta)
                if delta>2e-6:raise ValueError('Native observation parity failed: '+key)
            views+=1
    ppo_fixture = module_at('attention_ppo_fixture', ROOT/'tests/native_attention_ppo/generate_fixture.py')
    ppo_fixture.generate(run/'initial_actor.pt',run/'team_inputs.pt',run/'ppo_fixture')
    ppo_binary = binary_path(build_dir).parent / ('SlaterAttentionPPOParity.exe' if os.name=='nt' else 'SlaterAttentionPPOParity')
    ppo = checked_process([ppo_binary,run/'initial_actor.pt',run/'ppo_fixture',run/'ppo_result'],
                          run/'ppo_parity.log',marker='SLATER_ATTENTION_PPO_PARITY_COMPLETE')
    result.update(observation_views=views,observation_max_abs_error=max_error,ppo=ppo)
    result.update(python_observations=observations, source_unchanged=True)
    atomic_json(run / 'parity.json', result)
    return result


def evaluate(name, *, build_dir=None, checkpoint=None, seeds=8, seconds=60.):
    run, protocol = check_run(name, build_dir)
    checkpoint = complete_checkpoint(checkpoint) if checkpoint else latest_checkpoint(run)
    profile = validate_profile({**protocol['profile'], 'eval_seeds': seeds, 'seconds': seconds})
    folder = run / 'evaluations' / f'{checkpoint.name}_{time.time_ns()}'
    folder.mkdir(parents=True)
    command = native_command('eval', run, profile, build_dir=build_dir, checkpoint=checkpoint, updates=1)
    result = checked_process(command, folder / 'eval.log', marker='SLATER_ATTENTION_EVAL_COMPLETE')
    verify_protected(protocol)
    result.update(checkpoint=str(checkpoint), checkpoint_actor_sha256=sha256(checkpoint / 'actor.pt'),
                  playing_model=protocol['playing_model'], auto_promotion=False)
    atomic_json(folder / 'comparison.json', result)
    print('ATTENTION_EVALUATION_REPORT', folder / 'comparison.json', flush=True)
    return result


def export_checkpoint(name, *, checkpoint=None, output=None):
    run = run_path(name)
    protocol = read_json(run / 'protocol.json')
    if not protocol:
        raise ValueError('No saved native attention run')
    checkpoint = complete_checkpoint(checkpoint) if checkpoint else latest_checkpoint(run)
    output = Path(output or run / f'{checkpoint.name}_attention.pt').resolve()
    if not output.is_relative_to(BASE.resolve()):
        raise ValueError('Private exports must remain under data/isolated/native_attention')
    if output.exists():
        raise FileExistsError('Export exists; select a new output path')
    actor = torch.jit.load(str(checkpoint / 'actor.pt'), map_location='cpu')
    torch.save({'actor': actor.state_dict(), 'source': str(checkpoint),
                'native_attention_protocol_sha256': sha256(run / 'protocol.json')}, output)
    original = load_actor(ROOT, output)
    if not all(torch.equal(value, original.state_dict()[key]) for key, value in actor.state_dict().items()):
        output.unlink()
        raise RuntimeError('Export weight comparison failed')
    print('ATTENTION_EXPORT', output, flush=True)
    return output


def benchmark(name, source=DEFAULT_SOURCE, *, build_dir=None, profile=None, updates=3):
    """Collect actual native timing and a same-policy Python reference context.

    The bundled simulators differ. This deliberately makes no unqualified
    end-to-end speedup claim; use the phase measurements for local decisions.
    """
    profile = {**PROFILE, **(profile or {})}
    if profile['device'] != 'cpu':
        raise ValueError('Comparison benchmark requires --device cpu for both implementations')
    import random
    starts = []
    if updates * profile['games'] * profile['steps'] > 2000000:
        raise ValueError('Benchmark reset table would be too large; use a smaller comparison budget')
    for arena in range(profile['games']):
        for episode in range(updates * profile['steps'] + 1):
            seed = profile['seed'] + arena * 7919 + episode
            order = list(range(5)); random.Random(seed).shuffle(order)
            starts.append({'seed': seed, 'permutation': order})
    start_file = BASE / 'benchmark_starts' / (name + '.json')
    if start_file.exists():
        raise FileExistsError('Benchmark starts exist; preserve them and use a fresh run name')
    atomic_json(start_file, {'orders': starts})
    result = train(name, source, build_dir=build_dir, profile=profile, updates=updates, kickoffs=start_file)
    run = run_path(name)
    protocol = read_json(run / 'protocol.json')
    from slater_mechanics_env import collect_batched
    from slater_versatile_env import VersatileEnv, VersatileCritic
    from slater_ppo import trust_region_update
    actor = torch.jit.load(str(run / 'initial_actor.pt')).eval()
    teacher = torch.jit.load(str(run / 'teacher.pt')).eval()
    rival = torch.jit.load(str(run / 'rival.pt')).eval()
    torch.set_num_threads(1)
    cfg = protocol['profile']
    torch.manual_seed(cfg['seed'])
    critic = VersatileCritic()
    initial_checkpoint = complete_checkpoint(run / 'checkpoints/checkpoint_000000')
    native_critic = torch.jit.load(str(initial_checkpoint / 'critic.pt'), map_location='cpu')
    critic.load_state_dict(native_critic.state_dict(), strict=True)
    native_rng = torch.jit.load(str(initial_checkpoint / 'rng.pt'), map_location='cpu')
    torch.set_rng_state(native_rng.state_dict()['cpu'])
    actor_optimizer = torch.optim.Adam(actor.parameters(), lr=cfg['actor_lr'])
    critic_optimizer = torch.optim.Adam(critic.parameters(), lr=cfg['critic_lr'])
    envs = [VersatileEnv({'nexto': rival, 'frozen_start': teacher}, task_name='match',
                        max_seconds=cfg['seconds'], fixed_side='blue' if i % 2 == 0 else 'orange',
                        fixed_rival='nexto' if (i // 2) % 2 == 0 else 'frozen_start',
                        anchor_weight=cfg['teacher_weight']) for i in range(cfg['games'])]
    timings = []
    try:
        seeds = [cfg['seed'] + i * 7919 for i in range(cfg['games'])]
        observations = [env.reset(seed) for env, seed in zip(envs, seeds)]
        for update in range(updates):
            begin = time.perf_counter()
            rows, completed, observations, seeds, truncations = collect_batched(
                actor, critic, envs, observations, seeds, cfg['steps'])
            collected = time.perf_counter()
            metrics = trust_region_update(actor, teacher, critic, actor_optimizer, critic_optimizer,
                                          rows, 2, min(256, cfg['games'] * cfg['steps']),
                                          cfg['teacher_weight'], cfg['seed'] + update,
                                          target_kl=cfg['target_kl'])
            end = time.perf_counter()
            count = len(rows['action'])
            timings.append({'update': update+1, 'decisions': count,
                            'collection_seconds': collected-begin, 'ppo_seconds': end-collected,
                            'collection_decisions_per_second': count/(collected-begin),
                            'overall_decisions_per_second': count/(end-begin),
                            'timeout_bootstraps': truncations, 'ppo': metrics})
            print('ATTENTION_PYTHON_BENCHMARK', json.dumps(timings[-1]), flush=True)
    finally:
        for env in envs:
            env.close()
    report = {'native': result, 'python': timings, 'same_actor_initial_weights': True, 'same_critic_initial_weights': True,
              'same_cpu_sampling_rng': True, 'shared_kickoff_permutations_sha256': sha256(start_file),
              'games': cfg['games'], 'steps_per_game': cfg['steps'], 'policy_device': 'cpu',
              'comparability': {'strict_end_to_end_speedup_verified': False,
                  'python_rocketsim_version': version('rocketsim'), 'native_rocketsim_version': '2.1.1',
                  'limitations': ['Different simulator versions; subsequent sampled trajectories and minibatch ordering can differ.',
                                  'Native total includes checkpoint I/O; Python phase totals exclude checkpoint I/O.',
                                  'These are phase/workload measurements, not identical-trajectory speed ratios.']}}
    verify_protected(protocol)
    atomic_json(run / 'benchmark.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'smoke', 'train', 'resume', 'pause', 'status',
                                          'eval', 'benchmark', 'parity', 'export'))
    parser.add_argument('--run', default='update180_attention01')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--teacher', type=Path)
    parser.add_argument('--rival', type=Path)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--giga-source', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--updates', type=int, default=100)
    for key, default in PROFILE.items():
        parser.add_argument('--' + key.replace('_', '-'), type=type(default), default=default)
    args = parser.parse_args()
    if args.command == 'build':
        build(args.build_dir, args.giga_source, args.jobs)
    elif args.command == 'pause':
        run = run_path(args.run)
        if not (run / 'protocol.json').is_file():
            raise ValueError('No such native attention run')
        (run / 'PAUSE').touch()
        print('Pause requested; wait for SLATER_ATTENTION_COMPLETE and a complete checkpoint.')
    elif args.command == 'status':
        run = run_path(args.run)
        print(json.dumps({'progress': read_json(run / 'progress.json'),
                          'session': read_json(run / 'session_summary.json')}, indent=2))
    elif args.command == 'eval':
        evaluate(args.run, build_dir=args.build_dir, checkpoint=args.checkpoint,
                 seeds=args.eval_seeds, seconds=args.seconds)
    elif args.command == 'export':
        export_checkpoint(args.run, checkpoint=args.checkpoint, output=args.output)
    elif args.command == 'parity':
        parity(args.run, args.source, build_dir=args.build_dir, teacher=args.teacher, rival=args.rival)
    elif args.command == 'benchmark':
        cfg = {key: getattr(args, key) for key in PROFILE}
        cfg['device'] = 'cpu'
        benchmark(args.run, args.source, build_dir=args.build_dir, profile=cfg,
                  updates=3 if args.updates == 100 else args.updates)
    else:
        cfg = {key: getattr(args, key) for key in PROFILE}
        updates = args.updates
        if args.command == 'smoke':
            if args.run == 'update180_attention01':
                args.run = 'attention_smoke_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
            cfg.update(games=2, steps=32)
            if args.device == 'auto':
                cfg['device'] = 'cpu'
            updates = 2
        train(args.run, args.source, teacher=args.teacher, rival=args.rival, profile=cfg,
              build_dir=args.build_dir, updates=updates, resume=args.command == 'resume')


if __name__ == '__main__':
    main()
