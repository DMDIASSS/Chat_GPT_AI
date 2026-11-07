"""Native batched GigaLearn runner, validation, tuning, guards and exports."""
from __future__ import annotations
import argparse,copy,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from native_access import install_error_handler
install_error_handler()
NOVA=ROOT.parent/'novaforge'
if not NOVA.exists():NOVA=ROOT.parent/'NovaForge'
sys.path.insert(0,str(NOVA))

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,value):
 from nova.core import atomic_json
 atomic_json(path,value)
def sha(path):
 from nova.core import sha256
 return sha256(path)
def folder(name):
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,60}',name):raise ValueError('Use a simple run name')
 return (ROOT/'runs'/name).resolve()
def binary():
 explicit=os.environ.get('GIGAFORGE_EXE')
 candidates=[Path(explicit)] if explicit else []
 candidates += [ROOT/'native/GigaForge.exe',ROOT/'build/Release/GigaForge.exe',ROOT/'build/GigaForge.exe',ROOT/'build/GigaForge']
 for p in candidates:
  if p.is_file():return p.resolve()
 raise FileNotFoundError('Native executable absent. Run 0_SETUP_CPU.bat or 1_SETUP_GPU.bat to restore the pinned native runtime.')
def environment(threads=4):
 import torch
 env=dict(os.environ);lib=Path(torch.__file__).parent/'lib'
 env['PATH']=str(lib)+os.pathsep+str(Path(sys.base_prefix))+os.pathsep+env.get('PATH','')
 env['GIGAFORGE_TORCH_LIB']=str(lib);env['GIGAFORGE_SIM_THREADS']=str(threads)
 env['PYTHONHOME']=sys.base_prefix
 env['OMP_NUM_THREADS']='1';env['MKL_NUM_THREADS']='1'
 return env

def launch(recipe,*,log=None):
 import torch
 if torch.__version__.split('+')[0]!='2.9.1':raise RuntimeError('Use the pinned PyTorch 2.9.1 runtime')
 with tempfile.TemporaryDirectory(prefix='native_recipe_') as temp:
  path=Path(temp)/'recipe.json';write(path,recipe)
  cmd=[str(binary()),str(path)]
  env=environment(recipe.get('simulation_threads',4))
  output=Path(log).open('w',encoding='utf8') if log else None
  try:
   process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT if output else None,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,start_new_session=os.name!='nt')
   try:
    began=notice=time.monotonic()
    while process.poll() is None:
     time.sleep(.5)
     if log and 'evaluation' in recipe and time.monotonic()-notice>=10:
      with Path(log).open('rb') as progress:
       progress.seek(0,2);progress.seek(max(0,progress.tell()-4096));tail=progress.read().decode('utf8',errors='replace')
      lines=[line for line in tail.splitlines() if line.startswith('NATIVE_EVAL ')]
      print('NATIVE_EVAL_RUNNING:',int(time.monotonic()-began),'wall seconds;',lines[-1] if lines else 'loading models / starting physics',flush=True)
      notice=time.monotonic()
   except KeyboardInterrupt:
    stop=recipe.get('stop_file')
    if stop:
     Path(stop).touch();print('STOP requested. Waiting for a complete iteration and checkpoint.',flush=True)
     while process.poll() is None:
      try:time.sleep(.5)
      except KeyboardInterrupt:print('Still saving safely; wait for the process to finish.',flush=True)
    else:process.terminate();process.wait()
    raise
   if process.returncode:
    detail=Path(log).read_text(encoding='utf8')[-6000:] if log else ''
    raise RuntimeError('Native process failed '+str(process.returncode)+' '+detail)
  finally:
   if output:output.close()

def device(choice):
 import torch
 if choice=='auto':return 'cuda' if torch.cuda.is_available() else 'cpu'
 if choice=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable in this Python runtime. Run 1_SETUP_GPU.bat or use --device cpu.')
 return choice

def base_recipe(run,family,settings,*,mode='cross',stop_at=0):
 import rlgym.rocket_league.sim as sim
 state=read(run/'state.json')
 tuning=read(run/'tuning.json').get('by_family',{}).get(family,{}) if (run/'tuning.json').exists() else {}
 recipe=dict(family=family,hitbox='breakout' if family=='chronos' else 'octane',seed=settings['seed']+(family=='galactus')*100003,
  games=settings['games'][family],torch_threads=settings.get('torch_threads',1),simulation_threads=settings['simulation_threads'],
  gamma=.999,rollout=settings['rollout'],batch=settings.get('optimizer_batch',256),minibatch=settings['minibatch'],warmup_iterations=1,
  actor_lr=5e-6,critic_lr=3e-4,device=settings['device'],trajectory_seconds=60.,
  meshes=str(Path(sim.__file__).parent/'collision_meshes'),anchor=str(retained(run,family)),
  checkpoints=str(run/'checkpoints'/family),metrics_file=str(run/'metrics'/f'{family}.jsonl'),stop_file=str(run/'STOP'),stop_at=stop_at)
 if mode in ('cross','parent'):
  other=('galactus' if family=='chronos' else 'chronos') if mode=='cross' else family
  recipe['opponent']=descriptor(retained(run,other),other)
 for key in ('games','simulation_threads','torch_threads'):
  if key in tuning:recipe[key]=tuning[key]
 return recipe

def descriptor(path,family):return dict(name=family,family=family,hitbox='breakout' if family=='chronos' else 'octane',path=str(Path(path).resolve()))
def retained(run,family):return (run/read(run/'champions'/f'{family}.json')['path']).resolve()
def latest(run,family):
 root=run/'checkpoints'/family
 paths=[p for p in root.glob('*') if p.is_dir() and p.name.isdigit() and (p/'COMPLETE').is_file()]
 return max(paths,key=lambda p:int(p.name)) if paths else None

def verify_generation(path):
 from nova.giga_teachers import GigaNetwork
 import torch
 path=Path(path)
 info=read(path/'native.json') if (path/'native.json').exists() else None
 if info:
  for name,digest in info['files'].items():
   if sha(path/name)!=digest:raise ValueError('Native generation changed: '+str(path/name))
 family=info['family'] if info else None
 if family:
  actor=GigaNetwork(path,family)
  with torch.inference_mode():
   probe=actor(torch.zeros(2,225 if family=='chronos' else 258))
   if not torch.isfinite(probe).all():raise ValueError('Native checkpoint produced nonfinite logits')
 return info

def seal_generation(path,family):
 from nova.giga_teachers import GigaNetwork
 import torch
 path=Path(path)
 actor=GigaNetwork(path,family)
 with torch.inference_mode():
  x=actor(torch.zeros(2,225 if family=='chronos' else 258))
  if not torch.isfinite(x).all():raise ValueError('Nonfinite native model')
 files={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name!='native.json'}
 write(path/'native.json',dict(version='gigaforge-native-v1',family=family,hitbox='breakout' if family=='chronos' else 'octane',
  observation=225 if family=='chronos' else 258,actions=90,files=files))
 return path

def create(name='native01',choice='auto'):
 import torch
 from nova.teachers import fetch_teachers,verify_teacher
 run=folder(name)
 if (run/'state.json').exists():print('NATIVE_EXISTS: preserving '+str(run),flush=True);return run
 if run.exists():raise FileExistsError('Incomplete run exists; use another name')
 fetch_teachers(['chronos','galactus']);run.mkdir(parents=True)
 settings=dict(version='gigaforge-v1',seed=271031,device=device(choice),games={'chronos':32,'galactus':32},
  simulation_threads=min(4,os.cpu_count() or 1),torch_threads=1,rollout=8192,optimizer_batch=256,minibatch=256,block=32768,
  evaluation_pairs=4,confirmation_pairs=8,evaluation_seconds=60,goal=10.,potential_field=.35,potential_distance=.1,
  gamma=.999,actor_lr=5e-6,critic_lr=3e-4,epochs=2,guide_kl=.2,anchor_kl_limit=.08)
 (run/'metrics').mkdir(parents=True,exist_ok=True)
 write(run/'config.json',settings)
 for family in ('chronos','galactus'):
  target=run/'parents'/family;target.mkdir(parents=True)
  source=verify_teacher(family)
  for p in source.iterdir():
   if p.name in ('SHARED_HEAD.lt','POLICY.lt') or p.suffix in ('.txt','.md') or p.name=='LICENSE':shutil.copy2(p,target/p.name)
  seal_generation(target,family)
  write(run/'champions'/f'{family}.json',dict(path=str(target.relative_to(run)),reason='Retained original initialization; no unverified promotion'))
 write(run/'state.json',dict(cycle=0,task=0,status='ready',halt_reason=None,total_decisions=0,mode='cross'))
 write(run/'provenance.json',dict(config_sha256=sha(run/'config.json'),source_files={p.relative_to(ROOT).as_posix():sha(p) for p in list((ROOT/'src').glob('*'))+list((ROOT/'tools').glob('*.py'))+[Path(__file__)]},
  original_teachers={f:read(run/'parents'/f/'native.json') for f in ('chronos','galactus')},
  training_objective='first-goal: 10*outcome + gamma*Phi(next)-Phi(previous); terminal potential 0; trajectory timeouts bootstrap',
  notes=['New native optimizers; SB3 optimizers and the Forge public-context residual are not silently converted.',
   'Original Chronos is Breakout; Galactus V2 is Octane. No models are selected by vehicle appearance.',
   'GigaLearn RocketSim version is pinned by the source archive. Python actor-parity checks do not establish identical physics.',
   'Demo respawn randomness is native; bitwise trajectory reproducibility is not guaranteed.']))
 print('NATIVE_CREATED:',run,'Chronos=Breakout Galactus=Octane Device='+settings['device'],flush=True)
 return run

def evaluate(run,family,candidate,*,split='development',pairs=None,seconds=None):
 from nova.forge_eval import paired,summary,judgement
 settings=read(run/'config.json');state=read(run/'state.json')
 seed={'development':410000000,'confirmation':710000000,'test':1410000000}[split]+state['cycle']*1000000
 root=run/'evaluations';root.mkdir(exist_ok=True)
 output=root/(family+'_'+split+'_'+str(time.time_ns())+'.json')
 recipe=base_recipe(run,family,settings,mode='self')
 spec=dict(candidate=descriptor(candidate,family),baseline=descriptor(retained(run,family),family),
  opponents=[descriptor(run/'parents'/f,f) for f in ('chronos','galactus')],pairs=pairs or settings['evaluation_pairs'],
  seconds=seconds or settings['evaluation_seconds'],seed=seed,output=str(output),stop_file=str(run/'STOP'))
 recipe['evaluation']=spec;launch(recipe)
 result=read(output);result.update(family=family,split=split,candidate=read(candidate/'native.json'),baseline=read(retained(run,family)/'native.json'),
  summary=summary(result['trials']),baseline_summary=summary(result['baseline_trials']),statistics=paired(result['trials'],result['baseline_trials']))
 write(output,result)
 decision=judgement(result['statistics'],dict(minimum_delta=.03,per_opponent_tolerance=.15,regression_delta=.1))
 print('NATIVE_WDL',family,result['summary'],'reference',result['baseline_summary'],decision,flush=True)
 return decision,result

def guard(run,family,candidate):
 decision,result=evaluate(run,family,candidate)
 if decision=='improved':decision,result=evaluate(run,family,candidate,split='confirmation',pairs=read(run/'config.json')['confirmation_pairs'])
 if decision=='improved':
  protected=run/'champions/generations'/family/sha(candidate/'POLICY.lt')
  if not protected.exists():
   protected.parent.mkdir(parents=True,exist_ok=True)
   with tempfile.TemporaryDirectory(dir=protected.parent) as stage:
    stage=Path(stage)
    for file in ('POLICY.lt','SHARED_HEAD.lt'):shutil.copy2(candidate/file,stage/file)
    seal_generation(stage,family);stage.rename(protected)
  verify_generation(protected)
  write(run/'champions'/f'{family}.json',dict(path=str(protected.relative_to(run)),reason='Fresh paired confirmation passed; copied outside rotating checkpoints',statistics=result['statistics']))
 elif decision=='regressed':
  state=read(run/'state.json');state['halt_reason']=family+' regressed against retained champion';write(run/'state.json',state)
 write(run/f'latest_evaluation_{family}.json',result)
 return decision

def candidate_actor(run,family,candidate=False):
 import torch
 from nova.giga_teachers import GigaNetwork
 from nova.forge_models import DirectActor,save_actor
 if candidate and (run/'lab_state.json').exists():
  from research import candidate_source
  source=candidate_source(sys.modules[__name__],run,family)
 else:source=latest(run,family) if candidate else retained(run,family)
 if source is None:source=retained(run,family)
 verify_generation(source)
 actor=DirectActor(family);actor.core.load_state_dict(GigaNetwork(source,family).state_dict(),strict=True)
 target=run/'export_actors'/family/(sha(source/'POLICY.lt')[:12]+'.lt')
 if not target.exists():save_actor(actor,target,family,hitbox='breakout' if family=='chronos' else 'octane',
  source_native=read(source/'native.json'),role='unverified native candidate' if candidate else 'retained native champion')
 return target

def export(name,candidate=False):
 from nova.forge_export import export_actor_bundle
 run=folder(name)
 return [export_actor_bundle(candidate_actor(run,f,candidate),ROOT/'exports'/name,label='unverified candidate' if candidate else 'retained native champion') for f in ('chronos','galactus')]

def report(name):
 run=folder(name);destination=ROOT/'reports'/f'{name}_{time.time_ns()}.zip';destination.parent.mkdir(exist_ok=True)
 with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(run.rglob('*')):
   if p.is_file() and p.suffix in ('.json','.jsonl','.csv','.log') and not any(x in p.parts for x in ('export_actors','checkpoints','parents')):
    z.write(p,p.relative_to(run).as_posix())
 print('NATIVE_REPORT:',destination,flush=True);return destination

def train(name='native01',*,choice='auto',wandb='online',once=False):
 from filelock import FileLock
 from nova.tracking import Tracker
 run=create(name,choice);settings=read(run/'config.json');settings['device']=device(choice)
 write(run/'runtime_device.json',dict(device=settings['device'],torch_version=__import__('torch').__version__))
 if sha(run/'config.json')!=read(run/'provenance.json')['config_sha256']:raise ValueError('Training config changed; create a new experiment')
 if (run/'tuning.json').exists():
  tuning=read(run/'tuning.json');settings.update({k:tuning[k] for k in ('games','simulation_threads','torch_threads') if k in tuning})
 with FileLock(str(run/'train.lock'),timeout=0):
  state=read(run/'state.json')
  if state['halt_reason']:raise RuntimeError(state['halt_reason']+'; retained champions are preserved. Send the report for review.')
  (run/'STOP').unlink(missing_ok=True);tracker=Tracker(run,settings,mode=wandb,continuous=not once)
  try:
   while not (run/'STOP').exists():
    # Alternate cross-family adversaries, parent challenges, and current self-play.
    mode=('cross','parent','self')[state['cycle']%3];state['mode']=mode
    for index in range(state['task'],2):
     family=('chronos','galactus')[index];previous=latest(run,family)
     if previous:
      if not (previous/'native.json').exists():seal_generation(previous,family)
      verify_generation(previous)
      for required in ('CRITIC.lt','POLICY_OPTIM.lt','SHARED_HEAD_OPTIM.lt','CRITIC_OPTIM.lt','RUNNING_STATS.json'):
       if not (previous/required).is_file():raise ValueError('Incomplete resumable checkpoint: '+required)
     start=int(previous.name) if previous else 0
     key=family+'_'+str(state['cycle'])
     if state.get('block_key')!=key:state.update(block_key=key,block_target=start+settings['block'])
     write(run/'state.json',state)
     recipe=base_recipe(run,family,settings,mode=mode,stop_at=state['block_target'])
     for f in ('chronos','galactus'):verify_generation(retained(run,f))
     write(run/'status.json',dict(state='training',family=family,mode=mode,device=settings['device'],start=start,target=recipe['stop_at']))
     metrics=Path(recipe['metrics_file']);old=metrics.read_text().splitlines() if metrics.exists() else []
     t=time.monotonic();launch(recipe);elapsed=time.monotonic()-t
     current=latest(run,family)
     if current is None:raise RuntimeError('Native trainer returned without a complete checkpoint')
     seal_generation(current,family)
     rows=[json.loads(line) for line in metrics.read_text().splitlines()[len(old):]]
     for r in rows:
      tracker.log({family+'/'+k:v for k,v in r.items() if isinstance(v,(int,float))},state['total_decisions']+int(r['Total Timesteps'])-start)
     amount=int(current.name)-start;state['total_decisions']+=amount
     useful=sum(r.get('Used Timesteps',0) for r in rows)
     tracker.log({'throughput/end_to_end_training_decisions_per_second':amount/max(elapsed,1e-6),
      'throughput/end_to_end_useful_samples_per_second':useful/max(elapsed,1e-6)},state['total_decisions'])
     print(f'NATIVE_SPEED {family}: {amount/elapsed:.0f} collected, {useful/elapsed:.0f} useful samples/s including process loading and checkpoint save.',flush=True)
     if any(r.get('Guard Halt') for r in rows):state['halt_reason']='Native frozen-anchor KL guard halted '+family
     write(run/'state.json',state)
     if state['halt_reason'] or (run/'STOP').exists():break
     write(run/'status.json',dict(state='evaluating',family=family,mode=mode))
     decision=guard(run,family,current)
     refreshed=read(run/'state.json');state['halt_reason']=refreshed['halt_reason']
     state['task']=index+1;write(run/'state.json',state)
     export(name)
     if state['halt_reason']:break
    if state['halt_reason'] or (run/'STOP').exists():break
    state['cycle']+=1;state['task']=0;write(run/'state.json',state);report(name)
    if once:break
  except KeyboardInterrupt:
   (run/'STOP').touch();raise
  finally:
   state['status']='halted' if state['halt_reason'] else 'paused';write(run/'state.json',state)
   tracker.finish(state['status']);report(name)


def verify(name='native01',choice='auto'):
 import numpy as np,torch
 from nova.giga_teachers import GigaNetwork
 run=create(name,choice);settings=read(run/'config.json');settings['device']=device(choice)
 subprocess.run([str(binary()),'--selftest'],env=environment(),check=True)
 cases=read(NOVA/'tests/fixtures/giga_reference.json')['cases']
 from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
 with tempfile.TemporaryDirectory(prefix='native_verify_') as temp:
  temp=Path(temp);rows=[]
  for case in cases:
   s=deserialize_game_state(np.asarray(case['state'],np.float32));keys=list(s.cars);aid=next(k for k,p in s.cars.items() if p.team_num==case['side'])
   row=[keys.index(aid),*s.ball.position,*s.ball.linear_velocity,*s.ball.angular_velocity]
   for k in keys:
    p=s.cars[k];row.extend([p.team_num,*p.physics.position,*p.physics.linear_velocity,*p.physics.angular_velocity,*p.physics.rotation_mtx.T.flatten(),p.boost_amount,p.on_ground,p.has_jumped,p.has_flipped,p.has_double_jumped,p.air_time_since_jump,*(case['previous'] if k==aid else np.zeros(8))])
   row.extend([*s.boost_pad_timers,*np.asarray(case['predictions']).ravel()]);assert len(row)==140;rows.append(row)
  inputs=temp/'features.bin';np.asarray(rows,np.float32).tofile(inputs)
  for family,size in (('chronos',225),('galactus',258)):
   slots=temp/(family+'_slots.json');write(slots,[r['reference'][family]['opponent_slot'] for r in cases]);out=temp/(family+'.bin')
   subprocess.run([str(binary()),'--features',family,str(inputs),str(out),str(slots)],env=environment(),check=True)
   actual=np.fromfile(out,np.float32).reshape(len(cases),size+90+720)
   for i,case in enumerate(cases):
    ref=case['reference'][family]
    np.testing.assert_allclose(actual[i,:size],ref['features'],rtol=2e-6,atol=2e-6)
    np.testing.assert_array_equal(actual[i,size:size+90],ref['mask'])
    from nova.giga_teachers import TABLE
    np.testing.assert_array_equal(actual[i,size+90:].reshape(90,8),TABLE)
   recipe=base_recipe(run,family,settings,mode='self');recipe['checkpoints']=str(temp/family/'checkpoints')
   recipe.update(probe_input=np.asarray([r['reference'][family]['features'] for r in cases],np.float32).ravel().tolist(),probe_output=str(temp/(family+'_logits.json')),probe_only=True,games=2)
   launch(recipe,log=temp/(family+'.log'))
   network=GigaNetwork(Path(recipe['anchor']),family)
   with torch.inference_mode():expected=network(torch.tensor([r['reference'][family]['features'] for r in cases])).numpy()
   np.testing.assert_allclose(np.asarray(read(recipe['probe_output'])).reshape(-1,90),expected,rtol=3e-5,atol=5e-5)
 print('NATIVE_FEATURE_MASK_NETWORK_GAE_VERIFICATION_PASS',flush=True)
 write(run/'verification.json',dict(state='passed',device=settings['device'],binary_sha256=sha(binary()),cases=28))


def benchmark(name='native01',choice='auto'):
 run=create(name,choice);settings=read(run/'config.json');settings['device']=device(choice);results=[]
 for family in ('chronos','galactus'):
  for threads in sorted(set((min(4,os.cpu_count() or 1),min(6,os.cpu_count() or 1)))):
   for games in (16,32,64,128):
    with tempfile.TemporaryDirectory(prefix='native_benchmark_') as temp:
     temp=Path(temp);recipe=base_recipe(run,family,settings,mode='self')
     recipe.update(checkpoints='',games=games,simulation_threads=threads,benchmark_decisions=4096,benchmark_output=str(temp/'result.json'))
     launch(recipe,log=temp/'process.log');result=read(recipe['benchmark_output']);result['simulation_threads']=threads;results.append(result)
     print('NATIVE_BENCH',result,flush=True)
 # Rank settings by full PPO work, preserving two epochs and optimizer batch.
 full=[]
 for family in ('chronos','galactus'):
  candidates=sorted((r for r in results if r['family']==family),key=lambda r:r['collection_decisions_per_second'],reverse=True)[:2]
  for candidate in candidates:
   for torch_threads in (1,2,4):
    with tempfile.TemporaryDirectory(prefix='native_ppo_benchmark_') as temp:
     temp=Path(temp);recipe=base_recipe(run,family,settings,mode='cross')
     recipe.update(checkpoints='',games=candidate['games'],simulation_threads=candidate['simulation_threads'],torch_threads=torch_threads,
      metrics_file=str(temp/'metrics.jsonl'),max_iterations=3,stop_at=0,fixed_rollout=True)
     started=time.monotonic();launch(recipe,log=temp/'process.log');elapsed=time.monotonic()-started
     rows=[json.loads(r) for r in (temp/'metrics.jsonl').read_text().splitlines()]
     actor_steps=sum(r.get('Actor Optimizer Steps',0) for r in rows)
     if len(rows)!=3 or actor_steps==0:raise RuntimeError('Benchmark did not include actor learning')
     result=dict(family=family,games=recipe['games'],simulation_threads=recipe['simulation_threads'],torch_threads=torch_threads,
      seconds=elapsed,useful_samples_per_second=sum(r['Used Timesteps'] for r in rows)/elapsed,actor_optimizer_steps=actor_steps,metrics=rows)
     full.append(result);print('NATIVE_FULL_BENCH',family,result['useful_samples_per_second'],'useful samples/s',flush=True)
 selected={f:max((r for r in full if r['family']==f),key=lambda r:r['useful_samples_per_second']) for f in ('chronos','galactus')}
 # Keep per-family thread settings: a compromise can invalidate the measured winner.
 tuning=dict(games={f:selected[f]['games'] for f in selected},by_family=selected,collection=results,full_training=full,
  scope='Fixed-rollout full PPO, one critic warmup plus two actor iterations; epochs, network size and optimizer batch unchanged.')
 write(run/'tuning.json',tuning);print('NATIVE_TUNING_SAVED:',run/'tuning.json',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['create','verify','benchmark','train','pause','report','export','watch','status','research','h2h'])
 parser.add_argument('--run',default='native01');parser.add_argument('--device',choices=['auto','cpu','cuda'],default='auto');parser.add_argument('--wandb',choices=['online','offline','off'],default='online')
 parser.add_argument('--family',choices=['chronos','galactus'],default='chronos');parser.add_argument('--once',action='store_true');parser.add_argument('--hours',type=float);parser.add_argument('--candidate',action='store_true');parser.add_argument('--trial',type=int);parser.add_argument('--opponent',choices=['chronos','galactus']);parser.add_argument('--rounds',type=int,default=200);parser.add_argument('--seconds',type=float,default=100.);parser.add_argument('--batch-pairs',type=int,default=25);parser.add_argument('--seed',type=int,default=1580000000);args=parser.parse_args()
 if args.trial is not None and (args.command!='watch' or args.trial<0):parser.error('--trial requires watch and a nonnegative trial number')
 if args.opponent is not None and args.command!='watch':parser.error('--opponent is a watch option')
 import torch;torch.set_num_threads(1)
 explicit_run=any(a=='--run' or a.startswith('--run=') for a in sys.argv[1:])
 if args.command=='h2h':
  import head_to_head
  selected=args.run if explicit_run else (read(ROOT/'active_research.json')['run'] if (ROOT/'active_research.json').exists() else 'research02')
  head_to_head.run(sys.modules[__name__],selected,args.device,args.rounds,args.seconds,args.batch_pairs,args.seed)
  raise SystemExit(0)
 if args.command=='research':
  import research
  selected=args.run if explicit_run else (read(ROOT/'active_research.json')['run'] if (ROOT/'active_research.json').exists() else 'research02')
  research.train(sys.modules[__name__],selected,choice=args.device,wandb=args.wandb,once=args.once,hours=args.hours)
  raise SystemExit(0)
 if not explicit_run and args.command in ('pause','report','export','watch','status') and (ROOT/'active_research.json').exists():
  args.run=read(ROOT/'active_research.json')['run']
 if args.command in ('create','verify','benchmark'):globals()[args.command](args.run,args.device)
 elif args.command=='train':train(args.run,choice=args.device,wandb=args.wandb,once=args.once)
 elif args.command=='pause':(folder(args.run)/'STOP').touch();print('NATIVE_STOP_REQUESTED: wait for the current native iteration/checkpoint.')
 elif args.command=='report':report(args.run)
 elif args.command=='export':export(args.run,args.candidate)
 elif args.command=='status':print(json.dumps(read(folder(args.run)/'state.json'),indent=2))
 elif args.command=='watch':
  from nova.forge_export import watch
  from nova import forge_league
  run=folder(args.run);family=args.family
  label='candidate' if args.candidate else 'retained'
  if args.trial is not None:
   from trial_watch import prepare
   actor=prepare(sys.modules[__name__],run,family,args.trial);label=f'trial {args.trial} candidate (unverified)'
  else:actor=candidate_actor(run,family,args.candidate)
  # Read-only view folder, with a direct actor and its declared body.
  view=ROOT/'views'/args.run;view.mkdir(parents=True,exist_ok=True)
  cfg=read(NOVA/'configs/forge_league.json');cfg['hitboxes']={'chronos':'breakout','galactus':'octane'};write(view/'config.json',cfg)
  write(view/'champions'/f'{family}.json',dict(actor=str(actor)))
  original=forge_league.champion;original_path=forge_league.run_path
  try:
   forge_league.champion=lambda ignored,f:actor
   forge_league.run_path=lambda ignored:view
   print('NATIVE_WATCH:',family,'Breakout' if family=='chronos' else 'Octane',label,flush=True)
   watch(args.run,family,label=label,opponent=args.opponent)
  finally:forge_league.champion=original;forge_league.run_path=original_path
