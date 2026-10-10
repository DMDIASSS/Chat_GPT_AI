"""Research Hub staged curriculum: durable manifests, strict non-promotion gates."""
from __future__ import annotations
import json,os,pathlib,re,subprocess,sys,uuid,datetime,hashlib

HERE=pathlib.Path(__file__).resolve().parent
HUB=HERE.parent
GL=HUB.parent
PARENT=GL.parent
STAGES=['Replay imitation','TAS mechanics','Frozen Nexto/Cycle9/Wavedash','Competitive mechanics','Multi-agent curriculum','Heldout promotion']
BC_EXE=GL/'build_py311/Release/GigaLearnReplayBC.exe'

class GateError(RuntimeError):pass

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def new_id():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:7]
def latest_checkpoint(experiment):
    folder=HUB/'experiments'/experiment/'checkpoints'
    if not folder.is_dir():return None
    vals=[p for p in folder.iterdir() if p.is_dir() and p.name.isdecimal() and all((p/f).exists() for f in ('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json'))]
    return max(vals,key=lambda x:int(x.name)) if vals else None

def readiness():
    try:
        import hub_core
        available=hub_core.check_runtime()
    except Exception as ex:available={'note':'Could not read Hub runtime: '+str(ex)}
    data=PARENT/'data/replays'
    return {'existing_hub':HUB.is_dir(), 'cpp_source':(GL/'upstream/src/ExampleMain.cpp').is_file(),
         'replay_files':len(list(data.rglob('*.replay'))) if data.is_dir() else 0,
         'bc_exe':BC_EXE.is_file(),
         'trainer_exe':(GL/'build_py311/Release/GigaLearnBot.exe').is_file(),
         'gigalearn_eval':(GL/'build_py311/Release/GigaLearnEval.exe').is_file(),
         'original_nexto_models_read_only':True, 'native_nexto_cpp_bridge':False,
         'tas_aligned_state_controls':False,'multi_agent_cross_size_transfer':False,
         'runtime':available}

def mesh_path():
    mesh=os.environ.get('GIGALEARN_MESHES')
    if not mesh:
        mesh=str(PARENT/'.venv/Lib/site-packages/rlgym/rocket_league/sim/collision_meshes')
    if not pathlib.Path(mesh).is_dir():raise GateError('Collision meshes missing: '+mesh)
    return mesh

def environment():
    env=os.environ.copy();env['GIGALEARN_MESHES']=mesh_path()
    py=pathlib.Path(r'C:\Users\almas\AppData\Local\Programs\Python\Python311')
    if not py.is_dir():py=pathlib.Path(sys.base_prefix)
    env['PYTHONHOME']=str(py)
    env['PYTHONPATH']=os.pathsep.join((str(GL/'build_py311'),str(PARENT/'.venv/Lib/site-packages')))
    env['PATH']=os.pathsep.join((str(py),str(PARENT/'.venv/Lib/site-packages/torch/lib'),env.get('PATH','')))
    return env

def run_replay_bc(dataset_dir,*,epochs=4,lr=0.00008,seed_checkpoint=None,run_id=None):
    if not BC_EXE.is_file():raise GateError('C++ behavior cloning executable missing; install and build GigaLearnReplayBC first')
    root=pathlib.Path(dataset_dir)
    train=root/'replay_train.txt';val=root/'replay_val.txt'
    if not train.is_file() or not val.is_file():raise GateError('Replay files not prepared: '+str(root))
    if not 1<=epochs<=40 or not 1e-7<=lr<=5e-4:raise GateError('Unsafe imitation hyperparameters')
    name=run_id or new_id();dest=HERE/'results'/('replay_bc_'+name)
    if dest.exists():raise FileExistsError('Output already exists: '+str(dest))
    (HERE/'results').mkdir(exist_ok=True,parents=True)
    args=[str(BC_EXE),'--train',str(train),'--val',str(val),'--out',str(dest),
          '--epochs',str(epochs),'--lr',str(lr)]
    if seed_checkpoint:
        sd=pathlib.Path(seed_checkpoint)
        if not sd.is_dir() or not sd.name.isdecimal():raise GateError('Seed must be a numeric GigaLearn checkpoint directory')
        args+=['--seed-checkpoint',str(sd)]
    log=HERE/'results'/('replay_bc_'+name+'.log')
    if log.exists():raise FileExistsError('Run log already exists')
    with log.open('wb') as handle:
        result=subprocess.run(args,cwd=str(GL/'build_py311'),env=environment(),stdout=handle,stderr=subprocess.STDOUT)
    if result.returncode!=0:
        tail=log.read_text(encoding='utf8',errors='replace')[-3000:]
        raise GateError('Replay BC failed (exit '+str(result.returncode)+'): '+tail)
    report=dest/'report.json'
    if not report.is_file():raise GateError('Replay BC returned success without report')
    return json.loads(report.read_text(encoding='utf8'))

def branch_replay_to_hub(source,name,preset='Balanced 1v1'):
    """Copy an isolated C++ replay checkpoint into a brand-new Hub experiment."""
    sys.path.insert(0,str(HUB))
    import hub_core
    cp=pathlib.Path(source)
    if not cp.is_dir() or not cp.name.isdecimal():raise GateError('Choose numbered BC checkpoint folder')
    if preset not in hub_core.PRESETS:raise GateError('Unknown preset')
    settings=hub_core.PRESETS[preset]
    if (settings['blue'],settings['orange'])!=(1,1):raise GateError('Replay BC is ONLY 1v1; team-size transfer forbidden')
    return hub_core.new_experiment(name,preset,seed_dir=cp)

def stage_states():
    return [
      {'name':STAGES[0],'status':'experimental','description':'Filtered human replay inverse-control labels -> native GigaLearn .lt policy; MSVC smoke required'},
      {'name':STAGES[1],'status':'blocked','description':'TAS controls can be audited; no aligned per-tick game states or verified input semantics'},
      {'name':STAGES[2],'status':'blocked','description':'Frozen native Nexto/Cycle9/Wavedash .pt opponent adapter is not implemented; no fake match claims'},
      {'name':STAGES[3],'status':'available','description':'GigaLearn air, power, shooting, recovery, defense, kickoff presets, but evaluate before promotion'},
      {'name':STAGES[4],'status':'experimental','description':'GigaLearn team policies 1v2/1v3/2v2/3v3 train; cannot copy 1v1 network across team sizes'},
      {'name':STAGES[5],'status':'blocked','description':'Heldout gates require meaningful touches, shots and goals; initial all-draw evaluator insufficient'}]

def can_run_all():
    missing=[s['name'] for s in stage_states() if s['status']=='blocked']
    if missing:raise GateError('Full unattended curriculum is disabled; missing verified integrations: '+', '.join(missing))
    return True
