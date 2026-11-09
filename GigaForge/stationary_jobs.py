"""Native jobs with immutable identities, exact rounds, and safe bounded stopping."""
from pathlib import Path
import hashlib, json, math, os, subprocess, time

class PilotPaused(Exception):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def model_identity(m,path,family='chronos'):
    path=Path(path)
    return dict(family=family,hitbox='breakout' if family=='chronos' else 'octane',
                files={name:m.sha(path/name) for name in ('SHARED_HEAD.lt','POLICY.lt')})

def validate_rounds(rows,pairs,seed,seconds,opponent):
    if not 0<=seed<=2_000_000_000-pairs-10000:
        raise ValueError('Seed outside supported native range')
    expected={(seed+i,side) for i in range(pairs) for side in (0,1)}
    if len(rows)!=pairs*2 or {(r['seed'],r['side']) for r in rows}!=expected:
        raise ValueError('Missing, duplicate, or wrong seed/color in evaluation')
    for r in rows:
        if type(r['side']) is not int or type(r['seed']) is not int:
            raise ValueError('Invalid seed/color type')
        if r['opponent']!=opponent or abs(r['seconds']-seconds)>1e-7:
            raise ValueError('Wrong opponent or match duration')
        a,b=r['goals_for'],r['goals_against']
        if any(type(v) is not int or v<0 for v in (a,b)) or r['outcome']!=((a>b)-(a<b)):
            raise ValueError('Inconsistent score/outcome')

def summary(rows):
    from scipy.stats import t
    n=len(rows);w=sum(r['outcome']==1 for r in rows);d=sum(r['outcome']==0 for r in rows)
    blocks={}
    for r in rows:blocks.setdefault((r['opponent'],r['seed']),[]).append((r['outcome']+1)/2)
    means=[sum(v)/2 for v in blocks.values() if len(v)==2]
    ci=[None,None]
    if len(means)>1:
        mu=sum(means)/len(means);v=sum((x-mu)**2 for x in means)/(len(means)-1)
        half=float(t.ppf(.975,len(means)-1))*math.sqrt(v/len(means)) if v else math.sqrt(math.log(40)/(2*len(means)))
        ci=[max(0.,mu-half),min(1.,mu+half)]
    return dict(games=n,wins=w,draws=d,losses=n-w-d,
                score_rate=(w+.5*d)/n if n else None,score_interval_95=ci,
                goals_for=sum(r['goals_for'] for r in rows),goals_against=sum(r['goals_against'] for r in rows),
                paired_seed_blocks=len(means),interval_method='Approximate paired-seed Student-t; Hoeffding fallback for zero sample variance',
                automatic_promotion=False)

def paired_difference(rows,baseline):
    from scipy.stats import t
    key=lambda r:(r['opponent'],r['seed'],r['side'])
    a={key(r):r for r in rows};b={key(r):r for r in baseline}
    if len(a)!=len(rows) or len(b)!=len(baseline) or a.keys()!=b.keys():
        raise ValueError('Candidate/baseline paired keys differ')
    groups={}
    for k,r in a.items():groups.setdefault(k[:2],[]).append((r['outcome']-b[k]['outcome'])/2)
    if any(len(v)!=2 for v in groups.values()):raise ValueError('Missing paired color')
    values=[sum(v)/2 for v in groups.values()];n=len(values);mean=sum(values)/n
    ci=[None,None]
    if n>1:
        variance=sum((v-mean)**2 for v in values)/(n-1)
        half=float(t.ppf(.975,n-1))*math.sqrt(variance/n) if variance else math.sqrt(2*math.log(40)/n)
        ci=[max(-1.,mean-half),min(1.,mean+half)]
    return dict(delta=mean,interval_95=ci,paired_seed_blocks=n,scope='Development only; selected from two arms, not independent confirmation')

def process_rss_gib(pid):
    if os.name!='nt':
        try:
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                if line.startswith('VmRSS:'):return int(line.split()[1])/1024**2
        except OSError:return None
    else:
        import ctypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
                ('peak_rss','rss','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x0410,False,pid)
        if not handle:return None
        try:
            counters=Counters();counters.cb=ctypes.sizeof(counters)
            api=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
            api.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
            if api(handle,ctypes.byref(counters),ctypes.sizeof(counters)):return counters.rss/1024**3
        finally:kernel.CloseHandle(handle)
    return None

def resource_reason(min_free_gib=2.,max_gpu_temp=86.,max_gpu_mib=3584.,native_pid=None):
    """Use available telemetry; never claim an unavailable CPU temperature sensor."""
    free=None
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),
                      ('available',ctypes.c_ulonglong),('page_total',ctypes.c_ulonglong),('page_available',ctypes.c_ulonglong),
                      ('virtual_total',ctypes.c_ulonglong),('virtual_available',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]
        s=Memory();s.length=ctypes.sizeof(s)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):free=s.available/1024**3
    else:
        try:
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):free=int(line.split()[1])/1024**2
        except OSError:pass
    if free is not None and free<min_free_gib:return f'available RAM {free:.2f} GiB below {min_free_gib:g}'
    if native_pid:
        values=[process_rss_gib(p) for p in (os.getpid(),native_pid)]
        if all(v is not None for v in values) and sum(values)>=12.:
            return f'combined pilot/native resident memory {sum(values):.2f} GiB reached 12 GiB'
    try:
        r=subprocess.run(['nvidia-smi','--query-gpu=temperature.gpu,memory.used','--format=csv,noheader,nounits'],
                         capture_output=True,text=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if r.returncode==0:
            for line in r.stdout.strip().splitlines():
                temp,used=[float(v.strip()) for v in line.split(',')]
                if temp>=max_gpu_temp:return f'GPU temperature {temp:g} C reached {max_gpu_temp:g}'
                if used>=max_gpu_mib:return f'total GPU memory use {used:g} MiB reached {max_gpu_mib:g}'
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return None

def launch(m,recipe,directory,stop,deadline,*,metrics=None,guard=True):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if Path(stop).exists() or time.monotonic()>=deadline:raise PilotPaused('Pause or wall-time budget reached')
    if guard:
        problem=resource_reason()
        if problem:raise PilotPaused(problem)
    # New attempts never overwrite an interrupted recipe, output, or log.
    index=0
    while (directory/f'launch_{index:03d}.json').exists():index+=1
    m.write(directory/f'launch_{index:03d}.json',recipe)
    log=directory/f'launch_{index:03d}.log'
    command=[str(m.binary()),str(directory/f'launch_{index:03d}.json')]
    with log.open('w',encoding='utf8') as out:
        process=subprocess.Popen(command,cwd=m.ROOT,env=m.environment(recipe.get('simulation_threads',4)),
                                 stdout=out,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,
                                 start_new_session=os.name!='nt')
        notice=checked=time.monotonic();stopping=None;reason=None
        while process.poll() is None:
            try:
                now=time.monotonic()
                if now-checked>=10:
                    checked=now
                    if guard:reason=resource_reason(native_pid=process.pid)
                if now>=deadline:reason='Invocation wall-time budget reached'
                if reason or Path(stop).exists():
                    if stopping is None:
                        stopping=now;Path(stop).touch();print('PILOT_STOP:',reason or 'Pause requested','waiting for native checkpoint',flush=True)
                    elif now-stopping>120:
                        process.terminate();process.wait(timeout=20)
                        raise PilotPaused('Native stop exceeded 120s; prior completed checkpoints preserved; interrupted save is not accepted')
                if now-notice>=10:
                    notice=now;tail=''
                    if metrics and Path(metrics).is_file():
                        try:
                            with Path(metrics).open('rb') as f:
                                f.seek(0,2);f.seek(max(0,f.tell()-16384));lines=f.read().decode('utf8',errors='replace').splitlines()
                            row=json.loads(lines[-1]);tail=f"decisions={row.get('Total Timesteps')} useful_sps={row.get('Useful Samples/Second')}"
                        except (OSError,ValueError,IndexError):pass
                    elif 'evaluation' in recipe:
                        out.flush()
                        with log.open('rb') as f:
                            f.seek(0,2);f.seek(max(0,f.tell()-4096));lines=f.read().decode('utf8',errors='replace').splitlines()
                        status=[s for s in lines if s.startswith('NATIVE_EVAL ')];tail=status[-1] if status else 'loading evaluation'
                    print('PILOT_PROGRESS:',directory.name,tail,flush=True)
                time.sleep(.25)
            except KeyboardInterrupt:
                reason='Ctrl+C';Path(stop).touch()
                if stopping is None:stopping=time.monotonic()
                print('PILOT_STOP: Ctrl+C; waiting for a completed checkpoint',flush=True)
        if stopping is not None:raise PilotPaused(reason or 'Paused')
        if process.returncode:
            raise RuntimeError(f'Native job failed ({process.returncode}); {log}\n'+log.read_text(encoding='utf8',errors='replace')[-5000:])

def evaluate(m,study,candidate,opponent,family,opponent_family,opponent_name,*,pairs,seed,seconds,device,stop,deadline,guard=True):
    validate_rounds([],0,seed,seconds,opponent_name) # range check before loading anything
    if pairs<1 or seed+pairs+10000>2_000_000_000:raise ValueError('Unsupported evaluation seed/pairs')
    expected=dict(version='stationary-job-v1',native_sha256=m.sha(m.binary()),
                  candidate=model_identity(m,candidate,family),opponent=model_identity(m,opponent,opponent_family),
                  opponent_name=opponent_name,pairs=pairs,seed=seed,seconds=seconds,scenario='match',device=device)
    job=Path(study)/'evaluation_jobs'/digest(expected);job.mkdir(parents=True,exist_ok=True)
    completed=job/'completed.json'
    if completed.exists():
        receipt=m.read(completed)
        if receipt['identity']!=expected:raise ValueError('Cached evaluation identity changed')
        raw=job/receipt['output']
        if not raw.resolve().is_relative_to(job.resolve()):raise ValueError('Cached output path leaves its job directory')
        if m.sha(raw)!=receipt['output_sha256']:raise ValueError('Cached evaluation records changed')
        data=m.read(raw)
    else:
        attempt=0
        while (job/f'result_{attempt:03d}.json').exists():attempt+=1
        raw=job/f'result_{attempt:03d}.json'
        spec=dict(candidate=m.descriptor(candidate,family),opponents=[dict(m.descriptor(opponent,opponent_family),name=opponent_name)],
                  compare_baseline=False,pairs=pairs,seconds=seconds,seed=seed,scenario_mode='match',output=str(raw),stop_file=str(stop))
        import rlgym.rocket_league.sim as sim
        recipe=dict(evaluation=spec,device=device,torch_threads=1,simulation_threads=4,
                    meshes=str(Path(sim.__file__).parent/'collision_meshes'),stop_file=str(stop))
        launch(m,recipe,job,stop,deadline,guard=guard)
        if model_identity(m,candidate,family)!=expected['candidate'] or model_identity(m,opponent,opponent_family)!=expected['opponent']:
            raise ValueError('Model weights changed during evaluation')
        data=m.read(raw)
    if not data.get('direct_head_to_head') or data.get('baseline_trials') or data.get('evaluation_protocol')!='arena-rng-v4':
        raise ValueError('Unexpected native evaluation protocol or extra games')
    validate_rounds(data['trials'],pairs,seed,seconds,opponent_name)
    if not completed.exists():m.write(completed,dict(identity=expected,output=raw.name,output_sha256=m.sha(raw)))
    return data['trials']
