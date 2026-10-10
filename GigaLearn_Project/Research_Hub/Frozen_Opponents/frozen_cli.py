"""Fail-closed native Nexto/Cycle9/Wavedash PPO launcher. Safe, isolated 1v1 runs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
BASE=PROJECT.parent
EXPERIMENTS=HERE.parent/'experiments'
MODEL_FILENAMES=('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json')
DEFAULT_NEXTO=BASE/'vendor/nexto/nexto-model.pt'
DEFAULT_CYCLE9=BASE/'data/afk_improved/best_verified.pt'
DEFAULT_WAVEDASH=BASE/'data/mechanics/wavedash/last.pt'
EXECUTABLE=PROJECT/'build_py311/Release/GigaLearnBot.exe'


def filehash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def resolve_teachers(args):
    result={'nexto':Path(args.nexto), 'cycle9':Path(args.cycle9),'wavedash':Path(args.wavedash)}
    for n,p in result.items():
        if not p.is_file():
            raise FileNotFoundError(f'Missing {n} model: {p}')
    # These two checkpoints must contain actor-state dictionaries, verified by FrozenRotation.
    return result


def verify_seed(path):
    path=Path(path)
    if not path.is_dir(): raise NotADirectoryError(f'Seed checkpoint missing: {path}')
    for filename in MODEL_FILENAMES:
        p=path/filename
        if not p.is_file() or p.stat().st_size==0:
            raise RuntimeError(f'Incomplete 1v1 GigaLearn checkpoint: missing {p}')
    # Avoid training a state incompatible with GigaLearn; C++ will validate model architecture.
    stats=json.loads((path/'RUNNING_STATS.json').read_text(encoding='utf-8-sig'))
    if not isinstance(stats,dict): raise RuntimeError('Invalid RUNNING_STATS.json')
    return path


def create(args):
    name=args.name
    if not (3<=len(name)<=65 and all(c.isascii() and (c.isalnum() or c in '_-') for c in name)):
        raise ValueError('Experiment name must be 3..65 ASCII letters, digits, dash or underscore')
    seed=verify_seed(Path(args.seed).resolve())
    EXPERIMENTS.mkdir(parents=True,exist_ok=True)
    dst=EXPERIMENTS/name
    if dst.exists(): raise FileExistsError(f'Experiment already exists: {dst}')
    stage=EXPERIMENTS/('.creating_'+name)
    if stage.exists():raise FileExistsError('Prior unfinished experiment creation found: '+str(stage))
    try:
        cp=stage/'checkpoints'/'0'
        cp.mkdir(parents=True)
        hashes={}
        for f in seed.iterdir():
            if f.is_file() and (f.suffix=='.lt' or f.name=='RUNNING_STATS.json'):
                shutil.copy2(f,cp/f.name)
                hashes[f.name]=filehash(cp/f.name)
        for f in MODEL_FILENAMES:
            if f not in hashes:raise RuntimeError(f'Missing copied model file {f}')
        # Rebase training timesteps, retaining statistics and optimizer state.
        # Learner.Load() loads directory 0; counters are made zero so stage rotation starts at Nexto.
        stats=json.loads((cp/'RUNNING_STATS.json').read_text(encoding='utf-8-sig'))
        stats['total_timesteps']=0
        stats['total_iterations']=0
        stats.pop('run_id',None)
        (cp/'RUNNING_STATS.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
        hashes['RUNNING_STATS.json']=filehash(cp/'RUNNING_STATS.json')
        metadata={
            'name':name,'preset':'Frozen Nexto Rotation 1v1',
            'status':'created', 'created_utc':datetime.now(timezone.utc).isoformat(),
            'settings':{'mode':'balanced','blue':1,'orange':1,'lr':0.0001,'entropy':0.02,'setup':'random'},
            'notes':'New experimental GigaLearn student against frozen native Nexto actors. NOT competitive verified.',
            'seed_checkpoint':{'source_read_only':str(seed),'files':hashes},
            'parent_models_read_only':True,
            'frozen_bridge_config':{'teachers':['nexto','cycle9','wavedash'],'active':False},
        }
        (stage/'experiment.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        stage.rename(dst)
    except Exception:
        if stage.exists():shutil.rmtree(stage)
        raise
    print('SUCCESS: Created isolated student experiment:',dst)
    print('Original replay/TAS and teacher checkpoints were not modified.')


def latest_checkpoint(exp):
    folder=exp/'checkpoints'
    options=sorted((p for p in folder.iterdir() if p.is_dir() and p.name.isdigit()),
                   key=lambda p:int(p.name))
    if not options:raise RuntimeError('No checkpoint folders in '+str(folder))
    return options[-1]


def verify_install():
    # FROZEN_DLL_BUILD_GUARD_V1: Learner.cpp is compiled into GigaLearnCPP.dll,
    # not the launcher executable. Check compiled DLL freshness and embedded code.
    learner = PROJECT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
    header = PROJECT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Util/FrozenNextoBridge.h'
    if not learner.is_file() or 'FROZEN_NEXTO_BRIDGE_V1' not in learner.read_text(encoding='utf-8-sig'):
        raise RuntimeError('Run 1_INSTALL.bat first: Learner.cpp is not patched')
    if not header.is_file():
        raise RuntimeError('Missing frozen bridge header; run 1_INSTALL.bat / repair header')
    if not EXECUTABLE.is_file() or EXECUTABLE.stat().st_size == 0:
        raise FileNotFoundError('Run 2_BUILD.bat first: ' + str(EXECUTABLE))
    dll = EXECUTABLE.with_name('GigaLearnCPP.dll')
    if not dll.is_file() or dll.stat().st_size == 0:
        raise FileNotFoundError('Compiled GigaLearnCPP.dll missing; run 2_BUILD.bat: ' + str(dll))
    # Preserve a freshness check, but point it at the actual compiled artifact.
    latest_src = max(learner.stat().st_mtime, header.stat().st_mtime)
    if dll.stat().st_mtime + 2.0 < latest_src:
        raise RuntimeError('Compiled GigaLearnCPP.dll is older than patched source/header; run 2_BUILD.bat')
    # Ensure we didn't pick up an unrelated/stale DLL with a newer timestamp.
    dll_bytes = dll.read_bytes()
    for literal in (b'GL_FROZEN_BRIDGE', b'GL_FROZEN_STOP_AFTER_STEPS', b'GL_FROZEN_STEPS_PER_OPPONENT'):
        if literal not in dll_bytes:
            raise RuntimeError('Compiled GigaLearnCPP.dll lacks frozen teacher code ('
                               + literal.decode('ascii') + '); run 2_BUILD.bat')
    print('PASS: GigaLearnCPP.dll is fresh and contains frozen teacher bridge markers')


def preflight(args, require_binary=False):
    teachers=resolve_teachers(args)
    pkg=BASE/'.venv/Lib/site-packages'
    if pkg.is_dir(): os.environ['GL_FROZEN_SITE_PACKAGES']=str(pkg)
    import numpy as np
    from frozen_nexto_bridge import FrozenRotation
    model=FrozenRotation({k:str(p) for k,p in teachers.items()},FrozenRotation._original_actions())
    # Strict weights + torchscript + input/output shape smoke check.
    frame=np.zeros((1,89),dtype=np.float32)
    frame[:,:34]=1
    frame[:,34+2]=93
    for offset in (43,66):
        frame[:,offset+2]=17
        frame[:,offset+3]=frame[:,offset+7]=frame[:,offset+11]=1
        frame[:,offset+18]=33
        frame[:,offset+19]=frame[:,offset+20]=1
    frame[:,43+1]=-2400; frame[:,66+1]=2400
    for n in ('nexto','cycle9','wavedash'):
        model.select(n)
        actions=model.infer(frame,[1],True)
        if len(actions)!=1 or not 0<=actions[0]<90:raise AssertionError('Invalid '+n+' action')
        print(f'PASS {n}: model loads, makes 90-action inference; SHA {model.hashes[n][:16]}')
    if require_binary:verify_install()
    print('PASS frozen teacher preflight. Does not prove live C++ simulation works.')


def run(args):
    if args.save_every < 8192 or args.save_every > 262144 or args.save_every % 4096:
        raise ValueError('Checkpoint interval must be a 4096-multiple between 8192 and 262144')
    if not 1 <= args.run_seed <= 2000000000:
        raise ValueError('Seed must be 1..2000000000')
    verify_install()
    teachers=resolve_teachers(args)
    exp=EXPERIMENTS/args.name
    if not exp.is_dir():raise FileNotFoundError(f'Create the branch first: {exp}')
    if not (exp/'experiment.json').is_file():raise FileNotFoundError('Missing experiment metadata')
    cfg=json.loads((exp/'experiment.json').read_text(encoding='utf-8'))
    if cfg.get('preset')!='Frozen Nexto Rotation 1v1':
        raise RuntimeError('Refusing to run inside a non-frozen training experiment')
    checkpoint=latest_checkpoint(exp)
    old_step=int(checkpoint.name)
    if args.steps < 4096 or args.steps % 4096:
        raise ValueError('Use --steps as a positive multiple of 4096 (min 4096)')
    if args.rotation < 4096 or args.rotation % 4096:
        raise ValueError('Use --rotation as a multiple of 4096 (min 4096)')
    lock=exp/'launch.lock'
    try:
        with lock.open('x') as f: f.write(json.dumps({'pid':os.getpid(),'command':'frozen-rotation'}))
    except FileExistsError:
        raise RuntimeError('launch.lock exists; another process may be training this experiment. Refusing to start.')
    try:
        env=os.environ.copy()
        env.update({
            'GL_FROZEN_BRIDGE':'1','GL_FROZEN_BRIDGE_DIR':str(HERE),
            'GL_FROZEN_SITE_PACKAGES':str(BASE/'.venv/Lib/site-packages'),
            'GL_FROZEN_PYTHON_EXE':sys.executable,
            'GL_FROZEN_NEXTO_PT':str(teachers['nexto']),
            'GL_FROZEN_CYCLE9_PT':str(teachers['cycle9']),
            'GL_FROZEN_WAVEDASH_PT':str(teachers['wavedash']),
            'GL_FROZEN_STEPS_PER_OPPONENT':str(args.rotation),
            'GL_FROZEN_STOP_AFTER_STEPS':str(old_step+args.steps),
            'GL_HUB_HEADLESS':'1','GL_HUB_HISTORY':'0',
            'GL_HUB_BLUE':'1','GL_HUB_ORANGE':'1',
            'GL_HUB_MODE':'balanced','GL_HUB_SETUP':'random',
            'GL_HUB_STEPS_PER_ITER':'4096','GL_HUB_SAVE_EVERY':str(args.save_every), # GL_EXTENDED_SAVE_CONFIG_V1
            'GL_HUB_GAMES':str(args.games),'GL_HUB_ENTROPY':'0.02',
            'GL_HUB_LR':'0.0001','GL_HUB_SEED':str(args.run_seed),
        })
        # FROZEN_WORKER_SUBPROCESS_V1: subprocess must receive the project wheel packages.
        env['PYTHONPATH'] = str(BASE / '.venv/Lib/site-packages') + os.pathsep + env.get('PYTHONPATH','')
        if not env.get('GIGALEARN_MESHES'):
            env['GIGALEARN_MESHES']=str(BASE/'.venv/Lib/site-packages/rlgym/rocket_league/sim/collision_meshes')
        if not Path(env['GIGALEARN_MESHES']).is_dir():
            raise FileNotFoundError('RocketSim collision meshes missing. Set GIGALEARN_MESHES='+env['GIGALEARN_MESHES'])
        cfg['status']='running'
        (exp/'experiment.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
        logfile=exp/'reports/frozen_ppo.log'; logfile.parent.mkdir(exist_ok=True)
        print('Frozen opponent rotation:',args.rotation,'student steps per opponent')
        print('Student-only new timesteps:',args.steps,' starting at',old_step)
        print('Training cwd:',exp,'; log:',logfile)
        print('To save/stop at PPO boundary, create request_safe_stop.flag inside that experiment folder.')
        fatal_seen = False
        with logfile.open('a',encoding='utf-8') as log:
            with subprocess.Popen([str(EXECUTABLE)],cwd=exp,env=env,stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,encoding='utf-8',errors='replace') as proc:
                for line in proc.stdout:
                    if 'RG FATAL ERROR:' in line or 'Exception thrown during main learner loop:' in line:
                        fatal_seen = True
                    log.write(line); log.flush(); print(line,end='',flush=True)
                rc=proc.wait()
        if fatal_seen:
            rc = rc or 95
            print('ERROR: Trainer reported a fatal error; checkpoint cannot be marked successful')
        last=latest_checkpoint(exp)
        print('Final/latest checkpoint:',last)
        cfg['status']='exited_or_stopped' if rc==0 else 'error'
        cfg['last_frozen_return_code']=rc
        (exp/'experiment.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
        if rc:return rc
        if int(last.name) < old_step + args.steps:
            raise RuntimeError('No checkpoint reached requested new student steps; training did not complete')
        if int(last.name)<=old_step:
            raise RuntimeError('Trainer exited without a new saved student checkpoint; inspect frozen_ppo.log')
        print('SUCCESS: PPO student checkpoint saved; evaluate before promoting.')
        return 0
    finally:
        lock.unlink(missing_ok=True)


def make_parser():
    p=argparse.ArgumentParser(description='Research-only frozen Nexto-family opponent controller')
    p.add_argument('command',choices=('preflight','create','run'))
    p.add_argument('--nexto',type=Path,default=DEFAULT_NEXTO)
    p.add_argument('--cycle9',type=Path,default=DEFAULT_CYCLE9)
    p.add_argument('--wavedash',type=Path,default=DEFAULT_WAVEDASH)
    p.add_argument('--seed',type=Path,help='Exact GigaLearn 1v1 checkpoint directory to copy, never modified')
    p.add_argument('--name',default='nexto_rotation_01')
    p.add_argument('--steps',type=int,default=4096)
    p.add_argument('--rotation',type=int,default=4096)
    p.add_argument('--games',type=int,default=4)
    p.add_argument('--save-every',type=int,default=32768)
    p.add_argument('--run-seed',type=int,default=734891)
    return p

if __name__=='__main__':
    try:
        args=make_parser().parse_args()
        if args.command=='preflight':preflight(args)
        elif args.command=='create':
            if args.seed is None:raise ValueError('--seed checkpoint path is required')
            create(args)
        else:
            if not 1<=args.games<=16:raise ValueError('games must be 1..16')
            sys.exit(run(args))
    except Exception as e:
        print('ERROR:',e,file=sys.stderr)
        sys.exit(1)
