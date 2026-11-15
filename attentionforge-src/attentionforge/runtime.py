import json,os,hashlib,time,tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(obj,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def meshes():
    candidates=[os.environ.get('ATTENTIONFORGE_MESHES',''),os.environ.get('REPLICAR_MESHES','')]
    settings=ROOT/'local_paths.json'
    if settings.exists():candidates.append(json.loads(settings.read_text()).get('meshes',''))
    # Bounded locations: never scan all disks, user profiles, credentials or caches.
    for parent in (ROOT.parent,ROOT.parent.parent,Path.cwd()):
        for project in ('attention_forge','gigaforge','NovaForge','novaforge','RocketHive_Replicar_v2','RocketHive'):
            base=parent/project
            for rel in ('assets/collision_meshes','collision_meshes','third_party/collision_meshes','assets/meshes','native/collision_meshes'):
                candidates.append(str(base/rel))
    try:
        import importlib.util
        spec=importlib.util.find_spec('rlgym.rocket_league')
        if spec and spec.submodule_search_locations:candidates.append(str(Path(list(spec.submodule_search_locations)[0])/'sim/collision_meshes'))
    except (ImportError,ModuleNotFoundError,ValueError):pass
    for value in candidates:
        if value:
            p=Path(value)
            if p.is_dir() and any(p.rglob('*.cmf')):return p.resolve()
    raise FileNotFoundError('Soccar collision meshes not found. Set ATTENTIONFORGE_MESHES to your collision_meshes folder, or add {"meshes":"E:/.../collision_meshes"} to local_paths.json. Existing meshes are reused; game assets are not downloaded.')

def batch(cfg,n=None,seed=None,kickoffs=False):
    from . import _attention_native
    if cfg['rewards'].get('profile')=='rlgym_simple_v1' and getattr(_attention_native,'feature_version',0)<2:
        raise RuntimeError('The new native module was not loaded. Close trainers/watch windows, re-extract this update, then run SETUP.bat.')
    if cfg['rewards'].get('profile')=='control_shots_v1' and getattr(_attention_native,'reward_version',0)<1:
        raise RuntimeError('This reward experiment needs the new native module. Close Python trainers/watchers, re-extract the reward update, and run SETUP.bat.')
    if cfg['rewards'].get('profile')=='skills_v1' and getattr(_attention_native,'reward_version',0)<2:raise RuntimeError('Skills training requires the version 2 native reward module; re-extract and restart Python')
    if cfg['rewards'].get('profile')=='attack_v1' and getattr(_attention_native,'reward_version',0)<3:raise RuntimeError('Offense requires native reward version 3; re-extract and restart Python')
    return _attention_native.Batch(str(meshes()),int(n or cfg['n_envs']),int(cfg['team_size']),int(cfg['native_threads']),(int(cfg['seed'] if seed is None else seed) % (1<<32)),int(cfg['tick_skip']),int(cfg['action_delay']),float(cfg['ppo']['gamma']),float(cfg['episode_seconds']),float(cfg['no_touch_seconds']),cfg['rewards'],kickoffs)

def config(path=None):return json.loads(Path(path or ROOT/'config.json').read_text())

def device(cfg):
    import torch
    name=cfg.get('device','auto')
    if name=='auto':return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if name=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA requested but unavailable in this Python. Run SETUP.bat to select the existing CUDA environment.')
    return torch.device(name)

def save_checkpoint(path,payload):
    import torch
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='checkpoint_',suffix='.pt',dir=path.parent)
    os.close(fd)
    try:
        torch.save(payload,tmp)
        with open(tmp,'r+b') as f:f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def source_hashes():
    paths=list((ROOT/'attentionforge').glob('*.py'))+list((ROOT/'native').glob('*.cpp'))+list((ROOT/'native').glob('*.h'))+[ROOT/'config.json']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths if p.exists()}
