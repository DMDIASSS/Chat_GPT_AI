"""Isolated research manager for an existing GigaLearn C++ Windows build.
No Nexto PT conversion; no unexplained champion promotion or file deletion.
Python 3.11+, stdlib only.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PARENT = PROJECT.parent
EXPERIMENTS = HERE / 'experiments'
ROOT_EXE = PROJECT / 'build_py311' / 'Release' / 'GigaLearnBot.exe'
CYCLE9 = PARENT / 'data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
WAVEDASH = PARENT / 'data/mechanics/wavedash/last.pt'
PRESETS = {
    'Balanced 1v1': {'mode':'balanced','blue':1,'orange':1,'lr':0.00015,'entropy':0.035,'setup':'mixed'},
    'Precise Shooting 1v1': {'mode':'shooting','blue':1,'orange':1,'lr':0.00010,'entropy':0.025,'setup':'random'},
    'Defense Fundamentals 1v1': {'mode':'defense','blue':1,'orange':1,'lr':0.00010,'entropy':0.030,'setup':'random'},
    'Defense Under Pressure 1v2': {'mode':'defense','blue':1,'orange':2,'lr':0.00010,'entropy':0.030,'setup':'random'},
    'Defense Under Pressure 1v3': {'mode':'defense','blue':1,'orange':3,'lr':0.00008,'entropy':0.025,'setup':'random'},
    'Teamplay 2v2': {'mode':'balanced','blue':2,'orange':2,'lr':0.00010,'entropy':0.030,'setup':'random','historical_selfplay':True},
    'Teamplay 3v3': {'mode':'balanced','blue':3,'orange':3,'lr':0.00010,'entropy':0.030,'setup':'random','historical_selfplay':True},
    'Air Control Lab': {'mode':'air','blue':1,'orange':1,'lr':0.00008,'entropy':0.03,'setup':'random'},
    'Power Shot Lab': {'mode':'power','blue':1,'orange':1,'lr':0.00008,'entropy':0.03,'setup':'random'},
    'Recovery Lab': {'mode':'recovery','blue':1,'orange':1,'lr':0.00010,'entropy':0.03,'setup':'random'},
    'Kickoff Lab': {'mode':'balanced','blue':1,'orange':1,'lr':0.00012,'entropy':0.035,'setup':'kickoff'},
}

class HubError(RuntimeError):pass

def atomic_json(path:Path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.partial')
    with temp.open('w', encoding='utf8') as f:
        json.dump(obj,f,indent=2)
    os.replace(temp,path)

def read_json(path):return json.loads(Path(path).read_text(encoding='utf8'))

def sha256(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def now():return datetime.now(timezone.utc).isoformat()

def slug(text):
    result=re.sub(r'[^a-zA-Z0-9_-]+','_',text).strip('_').lower()[:60]
    if result in {'.','..'} or not result:raise HubError('Invalid experiment name')
    return result

def exp_path(name):return EXPERIMENTS/slug(name)

def get_preset(name):
    if name not in PRESETS:raise HubError('Unknown preset: '+name)
    return PRESETS[name]

def source_inventory():
    records=[]
    for label,path in [('Cycle9',CYCLE9),('Wavedash',WAVEDASH),('AFK verified',PARENT/'data/afk_improved/best_verified.pt')]:
        records.append({'label':label,'path':str(path),'exists':path.is_file(),'sha256_prefix':sha256(path)[:12] if path.is_file() else None,'compatible_with_gigalearn':False})
    return records

def new_experiment(name,preset,seed_dir=None,settings=None):
    p=exp_path(name)
    if p.exists():raise HubError('Experiment already exists. Refusing to overwrite: '+str(p))
    cfg={**get_preset(preset),**(settings or {})}
    if cfg['mode'] not in {'balanced','shooting','defense','air','power','recovery'}:raise HubError('Unsupported mode')
    if not(1<=int(cfg['blue'])<=3 and 1<=int(cfg['orange'])<=3):raise HubError('Team size must be 1..3 on each side')
    if not (0.000001<=float(cfg['lr'])<=0.001):raise HubError('LR out of range')
    if not (0<=float(cfg['entropy'])<=0.25):raise HubError('Entropy out of range')
    EXPERIMENTS.mkdir(parents=True,exist_ok=True)
    p.mkdir() # atomic; fails closed if another process created it
    try:
        (p/'checkpoints').mkdir()
        (p/'reports').mkdir()
        meta={'name':p.name,'preset':preset,'created_utc':now(),'status':'not_started','settings':cfg,
              'notes':'GigaLearn policy, not native Nexto. Validity of competitive improvement unverified.',
              'seed_checkpoint':None,'parent_models_read_only':True}
        if seed_dir:
            seed=Path(seed_dir).resolve()
            # AdvancedObs has player-count-dependent dimensions.
            # Do not load a 1v1 model into a 1v2/3v3 env until an explicit compatible adapter exists.
            owner_meta=seed.parent.parent/'experiment.json'
            if owner_meta.is_file():
                old=read_json(owner_meta)['settings']
                if (int(cfg['blue']),int(cfg['orange'])) != (int(old['blue']),int(old['orange'])):
                    raise HubError('Cannot seed across different team sizes: observation dimensions may differ. Start fresh or seed from the same mode.')
            elif (int(cfg['blue']),int(cfg['orange'])) != (1,1):
                raise HubError('External GigaLearn checkpoints are assumed 1v1; cannot seed 1v2/3v3 without verified observation compatibility.')
            if not seed.is_dir() or not (seed/'RUNNING_STATS.json').is_file():
                raise HubError('Seed must be a complete, numeric-timestep GigaLearn checkpoint folder')
            if not seed.name.isdecimal():raise HubError('Seed folder must be a numeric timesteps folder')
            needed=['POLICY.lt','POLICY_OPTIM.lt','SHARED_HEAD.lt','SHARED_HEAD_OPTIM.lt','CRITIC.lt','CRITIC_OPTIM.lt','RUNNING_STATS.json']
            missing=[x for x in needed if not (seed/x).is_file()]
            if missing:raise HubError('Incomplete GigaLearn checkpoint: '+', '.join(missing))
            # Guard against confusing native Nexto checkpoints with GigaLearn data.
            target=p/'checkpoints'/seed.name
            shutil.copytree(seed,target)
            meta['seed_checkpoint']={'source_read_only':str(seed),'files':{x:sha256(seed/x) for x in needed}}
            if any(sha256(target/x)!=meta['seed_checkpoint']['files'][x] for x in needed):
                raise HubError('Seed copy integrity check failed')
        atomic_json(p/'experiment.json',meta)
        return p
    except BaseException:
        # Only a newly-created experiment folder can be cleaned up.
        if (p/'experiment.json').exists(): pass
        elif p.is_dir(): shutil.rmtree(p)
        raise

def parse_metrics(folder):
    log=Path(folder)/'reports/training.log'
    if not log.is_file():return {'speed':None,'total_timesteps':None,'iterations':None}
    with log.open('rb') as f:
        f.seek(max(0,log.stat().st_size-50000))
        tail=f.read().decode('utf8',errors='replace')
    def last(pattern):
        a=re.findall(pattern,tail,re.I)
        return a[-1] if a else None
    return {
      'speed':last(r'Overall Steps/Second:\s*([\d,.]+)'),
      'total_timesteps':last(r'Total Timesteps:\s*([\d,]+)'),
      'iterations':last(r'Total Iterations:\s*([\d,]+)'),
    }

def list_experiments():
    if not EXPERIMENTS.exists():return []
    rows=[]
    for p in sorted(EXPERIMENTS.iterdir()):
        if p.is_dir() and (p/'experiment.json').exists():
            try:
                if (p/'running.json').exists():refresh_meta(p.name)
                meta=read_json(p/'experiment.json')
                checkpoints=[x for x in (p/'checkpoints').iterdir() if x.is_dir() and x.name.isdecimal()]
                rows.append({**meta,'checkpoints':len(checkpoints),'latest':max((int(x.name) for x in checkpoints),default=None), 'stop_requested':(p/'request_safe_stop.flag').exists(), **parse_metrics(p)})
            except Exception as e:rows.append({'name':p.name,'status':'error','error':str(e)})
    return rows

def hub_binary():
    override=os.environ.get('GIGALEARN_HUB_EXE')
    return Path(override) if override else ROOT_EXE

def check_runtime():
    root=hub_binary()
    mesh=os.environ.get('GIGALEARN_MESHES','')
    if not mesh:
        fallback=PARENT/'.venv/Lib/site-packages/rlgym/rocket_league/sim/collision_meshes'
        if fallback.is_dir():mesh=str(fallback)
    return {
        'binary':str(root),'binary_exists':root.is_file(),
        'binary_note':'Existing build requires Research Hub C++ patch + rebuild before environment profile settings and safe stop work.',
        'source':str(PROJECT/'upstream/src/ExampleMain.cpp'),
        'meshes':mesh,'meshes_exist':bool(mesh and Path(mesh).is_dir()),
        'torch_cmake':str(PARENT/'.venv/Lib/site-packages/torch/share/cmake/Torch/TorchConfig.cmake'),
        'models':source_inventory(),
        'python':sys.version.split()[0],
    }

def environment_for(cfg,exp):
    env=dict(os.environ)
    env.update({
      'GL_HUB_MODE':str(cfg['mode']),
      'GL_HUB_HEADLESS':'1',
      'GL_HUB_BLUE':str(cfg['blue']),
      'GL_HUB_ORANGE':str(cfg['orange']),
      'GL_HUB_LR':str(cfg['lr']),
      'GL_HUB_ENTROPY':str(cfg['entropy']),
      'GL_HUB_SETUP':str(cfg['setup']),
      'GL_HUB_HISTORY':'1' if cfg.get('historical_selfplay',False) else '0',
      'GL_HUB_GAMES':str(cfg.get('games',12)),
      'GL_HUB_STEPS_PER_ITER':str(cfg.get('steps_per_iter',4096)),
      'GL_HUB_SAVE_EVERY':str(cfg.get('save_every',50000)),
      'GL_HUB_SEED':str(cfg.get('seed',734891)),
      'PYTHONHOME':str(Path(sys.base_prefix)),
      'PYTHONPATH':os.pathsep.join([str(PROJECT/'build_py311'),str(PARENT/'.venv/Lib/site-packages')]),
    })
    mesh=check_runtime()['meshes']
    if mesh:env['GIGALEARN_MESHES']=mesh
    torch_lib=PARENT/'.venv/Lib/site-packages/torch/lib'
    env['PATH']=os.pathsep.join([str(Path(sys.base_prefix)),str(torch_lib),env.get('PATH','')])
    return env

def _require_patch():
    main=PROJECT/'upstream/src/ExampleMain.cpp'; learner=PROJECT/'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
    for f in (main,learner):
        if not f.is_file() or 'AFK_RESEARCH_HUB_PATCH_V1' not in f.read_text(encoding='utf-8-sig'):
            raise HubError('Research Hub C++ patch not installed or not rebuilt. Run Patch, then Build.')

def start_experiment(name):
    _require_patch()
    exe=hub_binary();p=exp_path(name)
    if not exe.is_file():raise HubError('C++ binary missing; compile build_py311')
    sources=[PROJECT/'upstream/src/ExampleMain.cpp',PROJECT/'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp']
    if exe.stat().st_mtime < max(x.stat().st_mtime for x in sources):
        raise HubError('Binary is older than C++ research patch. Rebuild build_py311 first.')
    meta=read_json(p/'experiment.json')
    pid_file=p/'running.json'
    if pid_file.exists():
        info=read_json(pid_file)
        if is_alive(info.get('pid')):raise HubError('Experiment appears to already be running (PID '+str(info['pid'])+')')
    stop=p/'request_safe_stop.flag'
    if stop.exists():raise HubError('Pending stop request exists: '+str(stop)+'; inspect before restart')
    launch_lock=p/'launch.lock'
    try:
        fd=os.open(launch_lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as e:
        raise HubError('Another app is launching this experiment. Check launch.lock and running.json.') from e
    try:
        if pid_file.exists() and is_alive(read_json(pid_file).get('pid')):
            raise HubError('Experiment already launched by another app')
        env=environment_for(meta['settings'],p)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with (p/'reports/training.log').open('ab',buffering=0) as log:
            proc=subprocess.Popen([str(exe)],cwd=str(p),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        atomic_json(pid_file,{'pid':proc.pid,'started_utc':now(),'exe':str(exe),'note':'safe stop via request_safe_stop.flag'})
        meta['status']='launched';meta['last_started_utc']=now();atomic_json(p/'experiment.json',meta)
        return proc.pid
    finally:
        os.close(fd)
        launch_lock.unlink(missing_ok=True)

def is_alive(pid):
    if not isinstance(pid,int) or pid<1:return False
    if os.name=='nt':
        r=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'],capture_output=True,text=True)
        return r.returncode==0 and f'"{pid}"' in r.stdout
    try:os.kill(pid,0);return True
    except OSError:return False

def request_safe_stop(name):
    p=exp_path(name);meta=read_json(p/'experiment.json')
    # C++ learner's loop watches this flag and saves after the current iteration.
    (p/'request_safe_stop.flag').write_text('Request save at PPO boundary; created '+now()+'\n',encoding='utf8')
    return p/'request_safe_stop.flag'

def refresh_meta(name):
    p=exp_path(name);meta=read_json(p/'experiment.json')
    rp=p/'running.json'
    if rp.exists():
        pid=read_json(rp).get('pid')
        if not is_alive(pid):
            meta['status']='exited_or_stopped';atomic_json(p/'experiment.json',meta)
            rp.unlink(missing_ok=True)
    return meta

def make_plan(base_path=None, variations=12):
    if variations not in (6,12,24):raise HubError('Variations must be 6/12/24')
    presets=['Balanced 1v1','Precise Shooting 1v1','Defense Under Pressure 1v2','Teamplay 2v2','Air Control Lab','Power Shot Lab','Recovery Lab','Kickoff Lab','Defense Under Pressure 1v3','Teamplay 3v3']
    lr_scales=[0.65,1.0,1.5]
    plan=[]
    for i in range(variations):
        name=presets[i%len(presets)]
        cfg=get_preset(name)
        cfg={**cfg,'lr':round(cfg['lr']*lr_scales[i%3],9),'seed':734891+i*1009,'games':12,'steps_per_iter':4096}
        plan.append({'name':f'ev_{i+1:02d}_{slug(name)}','preset':name,'settings':cfg,'status':'planned', 'parent_checkpoint':str(base_path) if base_path else None})
    atomic_json(HERE/'reports/evolution_plan.json',{'created_utc':now(),'purpose':'Isolated variants. Tournament evaluation and promotion NOT automated.','variants':plan})
    return plan

def replay_tas_audit():
    base=PARENT/'data/afk_improved'
    paths=[base/'learning/native_replay_dataset.npz',base/'learning/dataset_manifest.json',base/'learning/tas_audit.json']
    return {'native_replay_learning':'NOT supported by GigaLearn C++ policy in this release',
            'tas_learning':'NOT supported until verified states/actions, 120 Hz control and compatible imitation learner exist',
            'detected':[{'file':str(x),'exists':x.is_file()} for x in paths]}
