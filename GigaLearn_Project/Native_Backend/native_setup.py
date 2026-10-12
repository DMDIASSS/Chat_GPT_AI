"""Pinned GigaLearn build and bounded runs. Never treats Nexto .pt as an MLP."""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from slater_v041_core import atomic_json,read_json,sha256,process_lock
GIGA='86e11c3881a21225a43c36b14af40f0b3c87e7dd'
REPLICAR='a775fb1c4e5ee5c3079de3d0e6a16edb9335b71d'
BASE=ROOT/'data/isolated/gigalearn_native'


def command(args,**kwargs):
    print('RUN',subprocess.list2cmdline([str(a) for a in args]),flush=True)
    subprocess.run([str(a) for a in args],check=True,**kwargs)


def fetch(url,path,commit):
    path=Path(path)
    if not path.exists():command(['git','clone','-c','core.autocrlf=false','--depth','1',url,path])
    head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if head!=commit:
        if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True).strip():raise ValueError('Source checkout has local changes; choose a new folder')
        command(['git','-C',path,'fetch','--depth','1','origin',commit]);command(['git','-c','core.autocrlf=false','-C',path,'checkout','--detach',commit])
    return path


def patch_source(path):
    path=Path(path)
    if subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()!=GIGA:raise ValueError('Unexpected GigaLearn commit')
    manifest=read_json(HERE/'patch_manifest.json');states=[];normalized=[]
    for name,values in manifest.items():
        raw=(path/name).read_bytes()
        canonical=raw.replace(b'\r\n',b'\n')
        h=hashlib.sha256(canonical).hexdigest()
        if h==values['original']:states.append('original')
        elif h==values['patched']:states.append('patched')
        else:raise ValueError('Unexpected source contents (even after CRLF normalization): '+name+'; no blind overwrite')
        if raw!=canonical:normalized.append((path/name,canonical))
    # Validate every file before changing any bytes. Only known source text may
    # be normalized; a user edit or partial patch must leave the checkout intact.
    if len(set(states))!=1:raise ValueError('Partial patch; preserve checkout and use a fresh source folder')
    for file,canonical in normalized:file.write_bytes(canonical)
    if normalized:print('Normalized Windows CRLF line endings in',len(normalized),'verified source files.',flush=True)
    if set(states)=={'patched'}:print('Known compatibility patch already applied.');return
    command(['git','-C',path,'apply','--check',HERE/'compatibility.patch'])
    command(['git','-C',path,'apply',HERE/'compatibility.patch'])
    patched_files=[]
    for name,values in manifest.items():
        file=path/name;raw=file.read_bytes();canonical=raw.replace(b'\r\n',b'\n')
        if hashlib.sha256(canonical).hexdigest()!=values['patched']:
            raise ValueError('Patched source hash mismatch: '+name)
        if raw!=canonical:patched_files.append((file,canonical))
    # Git apply can honor core.autocrlf/eol attributes and write CRLF again.
    # Verify the actual output first, then canonicalize only known patched text.
    for file,canonical in patched_files:file.write_bytes(canonical)
    if patched_files:print('Normalized Git patch output line endings in',len(patched_files),'verified files.',flush=True)


def python_paths():
    base=Path(sys.base_prefix)
    if os.name=='nt':library=base/'libs'/f'python{sys.version_info.major}{sys.version_info.minor}.lib'
    else:library=base/'lib'/f'libpython{sys.version_info.major}.{sys.version_info.minor}.so'
    include=base/'include' if os.name=='nt' else base/'include'/f'python{sys.version_info.major}.{sys.version_info.minor}'
    if not library.exists() or not (include/'Python.h').exists():raise ValueError('Python development library/headers missing for '+sys.executable)
    return library,include


def meshes():
    import rlgym.rocket_league.sim.rocketsim_engine as engine
    path=Path(engine.__file__).parent/'collision_meshes'
    if not (path/'soccar').is_dir():raise ValueError('Existing RLGym collision meshes missing; supply --meshes')
    return path


def tool(name):
    local=Path(sys.executable).parent/(name+'.exe' if os.name=='nt' else name)
    found=str(local) if local.is_file() else shutil.which(name)
    if not found:raise ValueError('Install '+name+' in this Python environment')
    if not Path(found).is_file():raise ValueError('Install '+name+' in this Python environment')
    return found


def cuda_configuration(torch):
    env=os.environ.copy()
    if not torch.version.cuda:return [],env
    arch_list=env.get('TORCH_CUDA_ARCH_LIST','').strip()
    if not arch_list:
        if not torch.cuda.is_available():
            raise ValueError('CUDA-enabled Torch needs an explicit build architecture when no GPU is readable. Set TORCH_CUDA_ARCH_LIST to your GPU capability (for example 7.5), then rebuild.')
        arch_list=';'.join(sorted({f'{major}.{minor}' for major,minor in
            (torch.cuda.get_device_capability(i) for i in range(torch.cuda.device_count()))}))
    architectures=[]
    for token in re.split(r'[;\s]+',arch_list):
        match=re.fullmatch(r'(\d+)\.(\d+)([a-z]?)(?:\+PTX)?',token)
        if not match:raise ValueError('Use numeric TORCH_CUDA_ARCH_LIST values, for example 7.5 or 8.6+PTX')
        architectures.append(''.join(match.groups()))
    env['TORCH_CUDA_ARCH_LIST']=arch_list
    print('Explicit CUDA architectures:',arch_list,flush=True)
    return ['-DCMAKE_CUDA_ARCHITECTURES='+(';'.join(dict.fromkeys(architectures)))],env


def build(source,folder,jobs):
    import torch
    if not 1<=jobs<=8:raise ValueError('Use 1..8 compiler jobs')
    if os.name=='nt' and not shutil.which('cl'):raise ValueError('Open x64 Native Tools Command Prompt for VS 2022, or use NATIVE_2_BUILD.bat')
    cmake=tool('cmake')
    ninja=tool('ninja')
    cuda_args,build_env=cuda_configuration(torch)
    library,include=python_paths();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    command([cmake,'-S',HERE,'-B',folder,'-G','Ninja',f'-DGIGALEARN_SOURCE={Path(source).resolve()}',
        f'-DCMAKE_MAKE_PROGRAM={ninja}','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_PREFIX_PATH={torch.utils.cmake_prefix_path}',
        f'-DPython_EXECUTABLE={sys.executable}',f'-DPYTHON_EXECUTABLE={sys.executable}',
        f'-DPYTHON_LIBRARY={library}',f'-DPYTHON_INCLUDE_DIR={include}',*cuda_args],env=build_env)
    command([cmake,'--build',folder,'--target','SlaterGigaNative','-j',str(jobs)],env=build_env)


def parse_log(text):
    result={}
    for label in ('Collection Steps/Second','Overall Steps/Second'):
        values=[float(v.replace(',','')) for v in re.findall(re.escape(label)+r': ([\d,.]+)',text)]
        if not values or not all(v>0 for v in values):raise ValueError('No valid '+label+' measurements')
        warm=values[1:] or values;result[label]={'samples':values,'warm_median':sorted(warm)[len(warm)//2]}
    done=re.findall(r'SLATER_GIGA_COMPLETE iterations=(\d+) timesteps=(\d+)',text)
    if not done:raise ValueError('No verified completion marker; inspect training.log even if process returned zero')
    result['total_iterations'],result['total_timesteps']=map(int,done[-1]);return result


def runtime_environment(binary,pause,*,windows=None):
    env=dict(os.environ);env['SLATER_GL_PAUSE_FILE']=str(pause)
    if windows is None:windows=os.name=='nt'
    if windows:
        import torch
        build=Path(binary).resolve().parent
        directories=[build,build/'giga',Path(torch.__file__).resolve().parent/'lib',Path(sys.base_prefix)]
        if env.get('CUDA_PATH'):directories.append(Path(env['CUDA_PATH'])/'bin')
        paths=[str(p) for p in directories if p.is_dir()]
        env['PATH']=';'.join([*paths,env.get('PATH','')])
        print('Native DLL search directories:', ';'.join(paths),flush=True)
    return env


def process_result(text,code,logfile):
    status=f'0x{code & 0xffffffff:08X}'
    tail='\n'.join(text.splitlines()[-20:])[-4000:] or '(No output from native executable.)'
    if code:
        hint={0xC0000135:'A required DLL was not found.',0xC000007B:'A DLL has an incompatible format.',
              0xC0000142:'DLL initialization failed.',0xC0000005:'Native access violation.'}.get(code & 0xffffffff,'')
        raise RuntimeError(f'Native executable exited with code {code} ({status}). {hint}\nLog: {logfile}\n{tail}')
    try:return parse_log(text)
    except ValueError as exc:
        raise RuntimeError(f'Native executable returned zero but did not verify training: {exc}\nLog: {logfile}\n{tail}') from exc


def run(a,resume=False):
    if not a.run or not a.run.replace('_','').replace('-','').isalnum():raise ValueError('Use an ASCII run name')
    run=BASE/'runs'/a.run
    if run.exists() and not resume:raise FileExistsError('Run exists: use resume or a new run name')
    binary=Path(a.build_dir).resolve()/('SlaterGigaNative.exe' if os.name=='nt' else 'SlaterGigaNative')
    if not binary.is_file():raise ValueError('Build the native executable first')
    profile={'games':a.games,'steps':a.steps,'threads':a.threads,'players':a.players,'device':a.device,
             'width':a.width,'depth':a.depth,'bank':str(Path(a.replay_bank).resolve()) if a.replay_bank else None}
    if resume:
        saved=read_json(run/'protocol.json')
        if not saved:raise ValueError('No saved native run')
        profile=saved['profile']
    identity={'profile':profile,'binary_sha':sha256(binary),'gigalearn_commit':GIGA,
              'bank_sha':sha256(profile['bank']) if profile['bank'] else None}
    run.mkdir(parents=True,exist_ok=True)
    with process_lock(run/'runner.lock'):
        old=read_json(run/'protocol.json')
        if old and old!=identity:raise ValueError('Binary or dataset changed; use a new native run')
        if not old:
            if a.initial_checkpoint:
                source=Path(a.initial_checkpoint).resolve()
                if not source.is_dir() or not source.name.isdigit():raise ValueError('Initial checkpoint must be a native numbered .lt checkpoint directory')
                required=['POLICY.lt','CRITIC.lt','SHARED_HEAD.lt','RUNNING_STATS.json','POLICY_OPTIM.lt','CRITIC_OPTIM.lt','SHARED_HEAD_OPTIM.lt']
                if not all((source/f).is_file() for f in required):raise ValueError('Initial native checkpoint is incomplete; Nexto .pt is not compatible')
                shutil.copytree(source,run/'checkpoints'/source.name)
                atomic_json(run/'source_checkpoint.json',{'path':str(source),'hashes':{f:sha256(source/f) for f in required}})
            atomic_json(run/'protocol.json',identity)
        pause=run/'pause.flag';pause.unlink(missing_ok=True)
        args=[binary,'--meshes',a.meshes or meshes(),'--checkpoints',run/'checkpoints','--iterations',a.iterations]
        for k in ('games','steps','threads','players','device','width','depth'):args+=['--'+k,str(profile[k])]
        if profile['bank']:args+=['--replay-bank',profile['bank'],'--bc-epochs',str(0 if resume else a.bc_epochs)]
        env=runtime_environment(binary,pause)
        logfile=run/f'training_{time.time_ns()}.log';started=time.perf_counter()
        with logfile.open('w',encoding='utf8') as f:
            proc=subprocess.Popen([str(x) for x in args],cwd=a.build_dir,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            for line in proc.stdout:f.write(line);f.flush();print(line,end='',flush=True)
            code=proc.wait()
        text=logfile.read_text(encoding='utf8')
        try:result=process_result(text,code,logfile)
        except RuntimeError as exc:
            atomic_json(run/'failure.json',{'exit_code':code,'exit_hex':f'0x{code & 0xffffffff:08X}',
                'log':str(logfile),'error':str(exc)})
            raise
        latest=run/'checkpoints'/str(result['total_timesteps'])
        required=['POLICY.lt','CRITIC.lt','SHARED_HEAD.lt','RUNNING_STATS.json']
        if not all((latest/f).is_file() for f in required):raise ValueError('Completion did not produce a complete checkpoint')
        result.update(seconds=time.perf_counter()-started,log=str(logfile),checkpoint=str(latest),
            checkpoint_hashes={f:sha256(latest/f) for f in required},architecture='GigaLearn MLP; not native Nexto',
            warning='Throughput, not measured skill. No automatic parent-champion replacement.')
        atomic_json(run/'last_result.json',result);print('NATIVE_RUN_VERIFIED',json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('check','fetch','build','smoke','bench','train','resume','pause','replicar-setup','replicar-convert'))
    p.add_argument('--source',default=str(BASE/'source'));p.add_argument('--build-dir',default=str(BASE/'build'))
    p.add_argument('--jobs',type=int,default=2);p.add_argument('--run',default='native_smoke01')
    p.add_argument('--meshes');p.add_argument('--games',type=int,default=32);p.add_argument('--steps',type=int,default=16384)
    p.add_argument('--iterations',type=int,default=6);p.add_argument('--threads',type=int,default=2);p.add_argument('--players',type=int,default=1)
    p.add_argument('--device',choices=('cpu','cuda','auto'),default='cpu');p.add_argument('--width',type=int,default=128);p.add_argument('--depth',type=int,default=2)
    p.add_argument('--initial-checkpoint');p.add_argument('--replay-bank');p.add_argument('--bc-epochs',type=int,default=2)
    p.add_argument('--input');p.add_argument('--output');p.add_argument('--replicar-exe',default='replicar')
    a=p.parse_args()
    if a.command=='check':
        import torch
        library,include=python_paths()
        print(json.dumps({'python':sys.executable,'torch':torch.__version__,'torch_cuda_version':torch.version.cuda,'cuda_available':torch.cuda.is_available(),
            'compiler':shutil.which('cl') or shutil.which('g++'),'cmake':tool('cmake'),
            'python_library':str(library),'python_headers':str(include),'meshes':str(meshes()),
            'nexto_checkpoint_directly_loadable':False},indent=2));return
    if a.command=='fetch':fetch('https://github.com/ZealanL/GigaLearnCPP-Leak.git',a.source,GIGA);patch_source(a.source);return
    if a.command=='build':patch_source(a.source);build(a.source,a.build_dir,a.jobs);return
    if a.command=='replicar-setup':
        path=fetch('https://github.com/Rolv-Arild/replicar.git',BASE/'replicar_source',REPLICAR)
        command([sys.executable,'-m','pip','install','--no-deps',str(path/'python/v2')])
        if not shutil.which('cargo'):raise RuntimeError('Reader installed. Native converter requires Rust 1.97+; install official Rust toolchain, then rerun replicar-setup')
        command(['cargo','build','--locked','--release','-p','replicar-cli'],cwd=path);return
    if a.command=='replicar-convert':
        if not a.input or not a.output:p.error('--input and --output are required')
        exe=Path(BASE/'replicar_source/target/release'/('replicar.exe' if os.name=='nt' else 'replicar'))
        if not exe.exists():exe=Path(a.replicar_exe)
        command([exe,'convert',a.input,'-o',a.output,'--jobs',str(a.jobs),'--skip-existing','--rows','ticks','--tick-step','8','--meshes',a.meshes or meshes()]);return
    if a.command=='pause':
        paused_run=BASE/'runs'/a.run
        if not paused_run.exists():raise ValueError('No native run')
        (paused_run/'pause.flag').touch();print('Native pause requested; finishes current PPO iteration.');return
    if a.command=='smoke':
        a.games=8;a.steps=1024;a.iterations=2
        if a.run=='auto':a.run='native_smoke_'+str(time.time_ns())
    run(a,resume=a.command=='resume')

if __name__=='__main__':main()
