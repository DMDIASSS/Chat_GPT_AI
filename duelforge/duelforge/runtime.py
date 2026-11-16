import contextlib,hashlib,json,os,tempfile,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
CONTRACT='duelforge-109-v1-octane-120hz-skip8-delay7'

def atomic_json(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(payload,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def save(path,payload):
    import torch
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix='checkpoint_',suffix='.pt',dir=path.parent);os.close(fd)
    try:
        torch.save(payload,tmp)
        with open(tmp,'r+b') as f:f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def load(path,device='cpu'):
    import torch
    return torch.load(path,map_location=device,weights_only=False)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def actor_sha(state):
    h=hashlib.sha256()
    for name,x in sorted(state.items()):h.update(name.encode());h.update(x.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()

def source_hashes():
    files=list((ROOT/'duelforge').glob('*.py'))+list((ROOT/'native').glob('*'))+[ROOT/'config.json']
    return {str(p.relative_to(ROOT)):sha(p) for p in files if p.is_file()}

def config(path=None):return json.loads(Path(path or ROOT/'config.json').read_text())

def validate(cfg):
    if cfg['tick_skip']!=8 or cfg['action_delay']!=7:raise ValueError('This prototype requires skip8/delay7; use a new contract for timing changes')
    if cfg['rewards']['goal']!=1 or cfg['rewards']['potential']!=.25:raise ValueError('Fixed goal/potential weights differ from native implementation')
    if not 1<=cfg['n_envs']<=256 or not 1<=cfg['native_threads']<=4:raise ValueError('Arena/worker bounds exceeded')
    if not 0<=cfg['league']['history_fraction']<=.5:raise ValueError('History fraction must be 0..0.5')
    nf=cfg['league'].get('nexto_fraction',0)
    if not 0<=nf<=.5 or nf+cfg['league']['history_fraction']>.75:raise ValueError('Nexto fraction must be 0..0.5; total frozen fraction must not exceed 0.75')
    if cfg['ppo']['steps']<8 or cfg['ppo']['batch_size']<16:raise ValueError('PPO rollout/minibatch too small')
    if not 0<=cfg['rewards']['impulse']<=.1:raise ValueError('Impulse weight outside experimental range')
    es=cfg['ppo'].get('entropy_schedule')
    if es and (not 0<=es['end']<=es['start']<=.1 or es['decay_transitions']<=0):raise ValueError('Invalid bounded entropy schedule')
    bs=cfg.get('bootstrap',{})
    if bs.get('enabled') and (not 0<=bs['approach_weight']<=.02 or not 0<=bs['contact_weight']<=.25 or bs['fade_transitions']<=0):raise ValueError('Bootstrap weights/budget out of range')
    return cfg

def device(cfg):
    import torch
    name=cfg.get('device','auto');cuda=torch.cuda.is_available()
    if name=='cuda' and not cuda:raise RuntimeError('CUDA requested but unavailable; run 0_SETUP.bat to select your existing CUDA Python')
    return torch.device('cuda' if name=='auto' and cuda else 'cpu' if name=='auto' else name)

def meshes():
    values=[os.environ.get('DUELFORGE_MESHES'),os.environ.get('ATTENTIONFORGE_MESHES'),os.environ.get('REPLICAR_MESHES')]
    p=ROOT/'local_paths.json'
    if p.is_file():values.append(json.loads(p.read_text()).get('meshes'))
    for parent in (ROOT,ROOT.parent,ROOT.parent.parent):
        for project in ('gigaforge','attention_skills','attention_forge','NovaForge','novaforge','RocketHive_Replicar_v2','RocketHive'):
            for rel in ('assets/collision_meshes','collision_meshes','third_party/collision_meshes','assets/meshes','native/collision_meshes'):
                values.append(str(parent/project/rel))
    try:
        import importlib.util
        spec=importlib.util.find_spec('rlgym.rocket_league')
        if spec and spec.submodule_search_locations:values.append(str(Path(next(iter(spec.submodule_search_locations)))/'sim/collision_meshes'))
    except (ImportError,ValueError):pass
    for v in values:
        if v and Path(v).is_dir() and next(Path(v).rglob('*.cmf'),None):return str(Path(v).resolve())
    raise FileNotFoundError('Soccar collision meshes not found. Set DUELFORGE_MESHES or put {"meshes":"E:/.../collision_meshes"} in local_paths.json. Game assets are reused, not downloaded.')

def batch(cfg,n=None,seed=None,seconds=None):
    from . import _native
    validate(cfg)
    if _native.contract!=CONTRACT:raise RuntimeError('Wrong native module; close Python windows and re-extract the full prototype')
    return _native.Batch(meshes(),int(n or cfg['n_envs']),int(cfg['native_threads']),int(cfg['seed'] if seed is None else seed)%(1<<32),8,7,float(cfg['ppo']['gamma']),float(cfg['rewards']['impulse']),float(seconds or cfg['episode_seconds']),float(cfg['no_touch_seconds'] if seconds is None else seconds))

@contextlib.contextmanager
def lock(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);f=(folder/'trainer.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            f.seek(0);f.write(b'0');f.flush();f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('This run already has a trainer; pause it first')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('This run already has a trainer; pause it first')
        yield
    finally:f.close()

def model(folder,checkpoint=None,dev='cpu'):
    from .model import ActorCritic
    path=Path(checkpoint) if checkpoint else Path(folder)/'latest.pt'
    if not path.is_file():raise FileNotFoundError(f'Exact actor missing: {path}. No substitute bot was loaded.')
    import io,torch
    data=path.read_bytes();d=torch.load(io.BytesIO(data),map_location=dev,weights_only=False);d['_source_sha256']=hashlib.sha256(data).hexdigest()
    with torch.random.fork_rng(devices=[]):m=ActorCritic(d['config']['width']).to(dev).eval()
    m.load_state_dict(d['model']);return m,d,path

def pin(folder,path,label):
    import shutil
    folder=Path(folder);path=Path(path);data=path.read_bytes();h=hashlib.sha256(data).hexdigest();out=folder/'pins'/h/'actor.pt';out.parent.mkdir(parents=True,exist_ok=True)
    if not out.exists():
        fd,tmp=tempfile.mkstemp(prefix='pin_',suffix='.pt',dir=out.parent)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,out)
    if sha(out)!=h:raise ValueError('Pinned checkpoint hash mismatch')
    return out,h
