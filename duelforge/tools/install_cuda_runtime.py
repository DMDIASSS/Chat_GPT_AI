"""Create a project-owned CPython 3.11 CUDA runtime; preserve existing projects."""
import argparse,json,os,struct,subprocess,sys,tempfile,time,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OWNER='duelforge-cuda-291-cu126-v1'

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def choose_target():
    for suffix in ('','_2','_3','_4','_5'):
        target=ROOT/('.venv_cuda_291'+suffix);marker=target/'duelforge_cuda_owner.json'
        if target.is_symlink():continue
        if not target.exists():return target
        try:
            if json.loads(marker.read_text()).get('owner')==OWNER:return target
        except (OSError,ValueError):pass
    raise RuntimeError('Existing CUDA environment folders were preserved. Choose a new project folder before retrying.')

def capture_meshes():
    # Ask the currently verified runtime for its working mesh path. Copy only
    # the asset-path hint, never Torch/site-packages across environments.
    hint=ROOT/'runtime_python.txt'
    if not hint.is_file():return None
    exe=hint.read_text(encoding='utf-8-sig').strip()
    if not Path(exe).is_file():return None
    probe="import sys,json;sys.path.insert(0,sys.argv[1]);from duelforge.runtime import meshes;print(json.dumps({'meshes':meshes()}))"
    try:
        p=subprocess.run([exe,'-c',probe,str(ROOT)],capture_output=True,text=True,timeout=30)
        if p.returncode:return None
        value=json.loads(p.stdout.strip().splitlines()[-1])['meshes'];folder=Path(value)
        if folder.is_dir() and next(folder.rglob('*.cmf'),None):return str(folder.resolve())
    except (OSError,ValueError,KeyError,IndexError,subprocess.TimeoutExpired):pass
    return None

GPU_PROBE=r'''import sys,json,torch,numpy
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
assert torch.__version__=='2.9.1+cu126', 'Unexpected Torch version: '+torch.__version__
assert torch.cuda.is_available(), 'CUDA still unavailable in the new CUDA-enabled runtime'
from duelforge.model import ActorCritic
from duelforge.execution import make_optimizer
from duelforge.runtime import config
cfg=config();torch.set_num_threads(2);m=ActorCritic(cfg['width']).cuda();opt,backend=make_optimizer(m,cfg,torch.device('cuda'))
x=torch.randn(32,109,device='cuda');legal=torch.ones(32,90,device='cuda',dtype=torch.bool)
a,v=m(x,legal);loss=a.square().mean()+v.square().mean();opt.zero_grad(set_to_none=True);loss.backward();opt.step();torch.cuda.synchronize()
assert all(torch.isfinite(p).all().item() for p in m.parameters())
print('CUDA_TRAINING_PROBE_PASS:',torch.cuda.get_device_name(),'Torch',torch.__version__,'Adam',backend)
'''

def call(args,**kwargs):
    display=[str(a) for a in args]
    if '-c' in display:display[display.index('-c')+1]='<disposable CUDA training probe>'
    print('RUN:', ' '.join(display),flush=True);subprocess.run([str(a) for a in args],check=True,**kwargs)

def install():
    if sys.version_info[:2]!=(3,11) or struct.calcsize('P')!=8:raise RuntimeError('Run with 64-bit Python 3.11: py -3.11 tools/install_cuda_runtime.py')
    status=ROOT/'cuda_install_status.json';target=choose_target();python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python');meshes=capture_meshes();phase='create_environment'
    print('CUDA_ENVIRONMENT:',target,'; existing NovaForge and checkpoints are preserved.',flush=True)
    try:
        target.mkdir(parents=True,exist_ok=True);atomic(target/'duelforge_cuda_owner.json',{'owner':OWNER,'python':'3.11','torch':'2.9.1+cu126'})
        if not python.is_file():venv.EnvBuilder(with_pip=True).create(target)
        phase='install_dependencies';atomic(status,{'phase':phase,'environment':str(target),'training_started':False})
        call([python,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','torch==2.9.1+cu126','--index-url','https://download.pytorch.org/whl/cu126'])
        call([python,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','numpy==2.2.6','wandb==0.31.0'])
        phase='cuda_training_probe';call([python,'-c',GPU_PROBE,str(ROOT)],cwd=ROOT)
        if meshes:
            file=ROOT/'local_paths.json';paths=json.loads(file.read_text()) if file.is_file() else {};paths['meshes']=meshes;atomic(file,paths);print('REUSING_COLLISION_MESHES:',meshes,flush=True)
        phase='native_verify_and_selection'
        call([python,str(ROOT/'tools/setup_project.py'),'--python',python,'--require-cuda'],cwd=ROOT)
        atomic(status,{'phase':'complete','environment':str(target),'torch':'2.9.1+cu126','cuda_training_probe':True,'existing_mesh_path_reused':bool(meshes),'training_started':False,'checkpoint_modified':False})
        print('CUDA_INSTALL_PASS: run 31_RESUME_POTENTIAL_CUDA.bat. Existing actor/optimizer/counters resume; no critic reset.',flush=True)
        return target
    except Exception as ex:
        atomic(status,{'phase':phase,'environment':str(target),'error':str(ex),'training_started':False,'checkpoint_modified':False})
        raise

if __name__=='__main__':install()
