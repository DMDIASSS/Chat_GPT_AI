"""Serial reward/population search with native fixed rollouts and protected exports.

Inspired adaptations of PBRS, GAE/time-limit bootstrapping, PBT, teacher
regularization and league play. Not a reproduction of AlphaStar or a promise
that any finite run improves true playing strength.
"""
from __future__ import annotations
from pathlib import Path
import copy,json,math,random,shutil,time

ARMS=[
 dict(name='control',potential=[.35,.10,0,0,0],lr=5e-6,anchor=.2,freeze_shared=False),
 dict(name='attack',potential=[.35,.15,.25,.10,.05],lr=2.5e-6,anchor=.2,freeze_shared=True),
 dict(name='defense',potential=[.20,.15,.05,.40,.05],lr=2.5e-6,anchor=.3,freeze_shared=True),
 dict(name='possession',potential=[.15,.20,0,.15,.30],lr=2.5e-6,anchor=.3,freeze_shared=True),
]
DEFAULT=dict(version='reward-lab-v2',block=65536,rollout=8192,max_branch_decisions=524288,
 development_pairs=32,confirmation_pairs=128,evaluation_batch_pairs=32,
 seconds=60,minimum_delta=.03,opponent_tolerance=.10,goal_rate_tolerance=.25,
 confirmation_error_budget=.05,evolve_min_trials=3,
 arms=ARMS,history_size=6,default_hours=5,seed=271031)


def create(m,name='research02',choice='auto',config=None):
 run=m.folder(name).resolve()
 if (run/'lab_state.json').exists():return run
 if run.exists():raise FileExistsError('Choose a new research run name; existing experiments are not converted in place')
 cfg=copy.deepcopy(DEFAULT)
 if config:cfg.update(copy.deepcopy(config))
 if cfg['rollout']<256 or cfg['block']<2*cfg['rollout']:raise ValueError('Each branch block needs critic warmup plus actor updates')
 # Seed from protected retained actors, never from a halted latest candidate.
 source=m.folder('native01');ancestry={}
 # New studies may inherit approved research champions, never an experimental
 # candidate. A stopped/paused predecessor is read-only throughout this copy.
 if (config or {}).get('version',DEFAULT['version'])=='reward-lab-v2' and name!='research01':
  previous=m.folder('research01')
  if (previous/'lab_state.json').exists():
   from filelock import FileLock,Timeout
   try:
    with FileLock(str(previous/'train.lock'),timeout=0):
     status=m.read(previous/'lab_state.json')['status']
     if status not in ('training','evaluating'):source=previous
   except Timeout as error:raise RuntimeError('Pause research01 with 4_PAUSE and wait for it to finish before starting research02. No new study was created.') from error
 run=m.create(name,choice).resolve()
 if source!=run and (source/'state.json').exists():
  for family in ('chronos','galactus'):
   parent=m.retained(source,family);m.verify_generation(parent)
   target=run/'parents'/family
   for file in ('POLICY.lt','SHARED_HEAD.lt'):shutil.copy2(parent/file,target/file)
   m.seal_generation(target,family);ancestry[family]=dict(source=str(parent),sha256=m.sha(parent/'POLICY.lt'))
  if (source/'tuning.json').exists():shutil.copy2(source/'tuning.json',run/'tuning.json')
 m.write(run/'lab.json',cfg)
 m.write(run/'lab_state.json',dict(trial=0,total_decisions=0,status='ready',pending=None,branches={},arms={},payoff={},history=[],results=[],population={}))
 m.write(run/'lab_provenance.json',dict(config_sha256=m.sha(run/'lab.json'),ancestry=ancestry,
  objective='10*goal_outcome + gamma*Phi(next)-Phi(current); goal terminal potential zero; rollout boundary bootstraps',
  actor_contract='Original 225/258 public features; no privileged opponent controls at inference',
  native_required='fixed-rollout-v1',sources='RESEARCH_PAPERS.md',
  code_sha256={p.resolve().relative_to(m.ROOT.resolve()).as_posix():m.sha(p) for p in [Path(__file__),m.ROOT/'research_eval.py',m.ROOT/'research_pacing.py',m.ROOT/'run.py',m.ROOT/'tools/patch_upstream.py',*sorted((m.ROOT/'src').glob('*'))] if p.is_file()}))
 print('RESEARCH_CREATED:',run,'Chronos=Breakout Galactus=Octane; old native01 preserved.',flush=True)
 return run


def choose_arm(state,family,arms):
 # Evaluate every arm, then favor measured external WDL with an exploration bonus.
 counts=[state['arms'].get(family+'/'+a['name'],{}).get('n',0) for a in arms]
 if 0 in counts:return arms[counts.index(0)]
 total=sum(counts)
 def ucb(a):
  item=state['arms'][family+'/'+a['name']]
  return item['score']/item['n']+.15*math.sqrt(math.log(1+total)/item['n'])
 return max(arms,key=ucb)


def pool(m,run,state,family):
 entries=[dict(m.descriptor(run/'parents'/f,f),name='original_'+f) for f in ('chronos','galactus')]
 for f in ('chronos','galactus'):
  current=m.retained(run,f)
  if current!=(run/'parents'/f).resolve():entries.append(dict(m.descriptor(current,f),name='champion_'+f+'_'+m.sha(current/'POLICY.lt')[:8]))
 for i,h in enumerate(state['history'][-4:]):entries.append(dict(m.descriptor(run/h['path'],h['family']),name='history_'+h['family']+'_'+m.sha(run/h['path']/'POLICY.lt')[:8]))
 return entries


def choose_opponent(entries,payoff,rng):
 hardness=[]
 for entry in entries:
  row=payoff.get(entry['name'],{})
  score=(row.get('points',0)+1)/(row.get('games',0)+2)
  hardness.append((1-score)**2)
 total=max(1e-12,sum(hardness))
 weights=[.2/len(entries)+.8*x/total for x in hardness]
 return rng.choices(entries,weights=weights,k=1)[0]


def stats(trials,baseline):
 from nova.forge_eval import paired
 from scipy.stats import t
 result=paired(trials,baseline)
 counts={}
 for row in trials:counts.setdefault(row['opponent'],set()).add(row['seed'])
 df=min(len(v) for v in counts.values())-1
 if result['standard_error'] is None or df<1:result.update(lower=None,upper=None)
 else:
  margin=max(1e-6,float(t.ppf(.975,df))*result['standard_error'])
  result.update(lower=result['delta']-margin,upper=result['delta']+margin)
 result['caution']='Approximate 95% paired Student-t interval; adaptive repeated testing is not a lifetime performance guarantee.'
 return result


def decision(result,cfg):
 s=result['statistics']
 if s['lower'] is None:return 'uncertain'
 if s['lower']>0 and s['delta']>=cfg['minimum_delta'] and min(s['by_opponent'].values())>=-cfg['opponent_tolerance']:
  # A goal-difference guard supplements the WDL measure.
  a=result['summary'];b=result['baseline_summary']
  if (a['goals_for']-a['goals_against']-(b['goals_for']-b['goals_against']))/max(1,a.get('matches',1))>=-.25:return 'improved'
 if s['upper']<0:return 'regressed'
 return 'uncertain'


def evaluate(m,run,state,family,candidate,split,cfg,tracker):
 if cfg['version']=='reward-lab-v2':
  from research_eval import evaluate as evaluate_v2
  return evaluate_v2(m,run,state,family,candidate,split,cfg,tracker)
 from nova.forge_eval import summary
 settings=m.read(run/'config.json');settings['device']=state['device']
 panel=[dict(m.descriptor(run/'parents'/f,f),name='original_'+f) for f in ('chronos','galactus')]
 other='galactus' if family=='chronos' else 'chronos'
 current_other=m.retained(run,other)
 if current_other!=(run/'parents'/other).resolve():panel.append(dict(m.descriptor(current_other,other),name='accepted_'+other+'_'+m.sha(current_other/'POLICY.lt')[:8]))
 spec=dict(candidate=m.descriptor(candidate,family),baseline=m.descriptor(m.retained(run,family),family),
  opponents=panel,
  pairs=cfg['confirmation_pairs'] if split=='confirmation' else cfg['development_pairs'],seconds=cfg['seconds'],
  seed=(710000000 if split=='confirmation' else 410000000)+state['trial']*10000,
  output=str(run/'evaluations'/f'lab_{state["trial"]:05d}_{family}_{split}.json'),stop_file=str(run/'STOP'))
 Path(spec['output']).parent.mkdir(exist_ok=True)
 recipe=m.base_recipe(run,family,settings,mode='self');recipe['evaluation']=spec;m.launch(recipe)
 result=m.read(spec['output']);result.update(family=family,split=split,summary=summary(result['trials']),
  baseline_summary=summary(result['baseline_trials']),statistics=stats(result['trials'],result['baseline_trials']))
 result['decision']=decision(result,cfg);m.write(spec['output'],result)
 log={f'evaluation/{family}/{split}/candidate_score':result['summary']['score_rate'],
  f'evaluation/{family}/{split}/baseline_score':result['baseline_summary']['score_rate'],
  f'evaluation/{family}/{split}/paired_delta':result['statistics']['delta'],
  f'evaluation/{family}/{split}/goal_difference':result['summary']['goals_for']-result['summary']['goals_against']}
 for bound in ('lower','upper'):
  if result['statistics'][bound] is not None:log[f'evaluation/{family}/{split}/{bound}']=result['statistics'][bound]
 tracker.log(log,state['total_decisions'])
 print('RESEARCH_WDL',family,split,result['summary'],'baseline',result['baseline_summary'],result['decision'],flush=True)
 return result


def protect(m,run,state,family,candidate,result):
 # Copy out of rotating checkpoints before changing the champion pointer.
 target=run/'champions/generations'/family/m.sha(candidate/'POLICY.lt')
 if not target.exists():
  target.mkdir(parents=True)
  for name in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(candidate/name,target/name)
  m.seal_generation(target,family)
 m.verify_generation(target)
 previous=m.retained(run,family)
 state['history'].append(dict(family=family,path=str(previous.relative_to(run))))
 state['history']=state['history'][-6:]
 m.write(run/'champions'/f'{family}.json',dict(path=str(target.relative_to(run)),reason='Reward lab: fresh paired confirmation passed',statistics=result['statistics']))


def persist(m,run,state):
 m.write(run/'lab_state.json',state)
 m.write(run/'status.json',dict(state=state['status'],trial=state['trial'],family=(state.get('pending') or {}).get('family'),arm=(state.get('pending') or {}).get('arm',{}).get('name')))
 common=m.read(run/'state.json');common.update(cycle=state['trial'],total_decisions=state['total_decisions'],status=state['status'],halt_reason=None)
 m.write(run/'state.json',common)


def latest_in(branch):
 root=Path(branch)/'checkpoints'
 paths=[p for p in root.glob('*') if p.name.isdigit() and p.is_dir() and (p/'COMPLETE').is_file()]
 return max(paths,key=lambda p:int(p.name)) if paths else None


def candidate_source(m,run,family):
 state=m.read(run/'lab_state.json');entry=state.get('last_candidates',{}).get(family)
 return run/entry if entry else m.retained(run,family)


def preserve_promising(m,run,state,family,candidate,result):
 """Keep two best positive-screen actors per family outside native rotation."""
 if result['statistics'].get('delta',0)<=0:return
 entries=state.setdefault('shortlist',{}).setdefault(family,[])
 rank=lambda item:(item['statistics'].get('lower') if item['statistics'].get('lower') is not None else -10,item['statistics']['delta'])
 from research_eval import digest
 actor_hash=digest({n:m.sha(candidate/n) for n in ('SHARED_HEAD.lt','POLICY.lt')})
 item=dict(trial=state['trial'],statistics=result['statistics'],sha256=actor_hash,verified_champion=False)
 item['path']=str(Path('shortlist')/family/item['sha256'])
 if any(v['sha256']==item['sha256'] for v in entries):return
 if len(entries)>=2 and rank(item)<=min(map(rank,entries)):return
 target=run/item['path']
 if not target.exists():
  target.mkdir(parents=True)
  for name in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(candidate/name,target/name)
  m.seal_generation(target,family)
 m.verify_generation(target);entries.append(item);entries.sort(key=rank,reverse=True)
 removed=entries[2:];del entries[2:]
 for old in removed:
  path=run/old['path']
  if path.is_dir() and not path.is_symlink() and path.resolve().is_relative_to((run/'shortlist'/family).resolve()):shutil.rmtree(path)
 m.write(run/'shortlist'/f'{family}.json',entries)


def evolve(state,cfg):
 """Bounded PBT-inspired coefficient search; goal reward and base control stay fixed."""
 for family,population in state.get('population',{}).items():
  if any(state['arms'].get(family+'/'+a['name'],{}).get('n',0)<cfg.get('evolve_min_trials',1) for a in population):continue
  def score(a):
   item=state['arms'][family+'/'+a['name']];return item['score']/item['n']
  winner=max(population,key=score);loser=min((a for a in population if a['name']!='control'),key=score)
  rng=random.Random(cfg['seed']+state['trial']+(family=='galactus')*10007)
  child=copy.deepcopy(winner);child['name']='evolved_'+str(state['trial'])
  child['potential']=[max(0.,min(.6,x*rng.choice([.8,1.2]))) for x in child['potential']]
  index=rng.randrange(2,5)
  if child['potential'][index]==0:child['potential'][index]=.1
  child['lr']=max(5e-7,min(5e-6,child['lr']*rng.choice([.8,1.2])))
  child['freeze_shared']=True
  population[population.index(loser)]=child
  print('RESEARCH_NEW_REWARD:',family,child,flush=True)


def prune_branches(m,run,state):
 """Prune only retired experiment checkpoints; champions and current candidates stay."""
 active_keys={family+'/'+a['name'] for family,arms in state.get('population',{}).items() for a in arms}
 protected={str((run/v['active_path']).resolve()) for key,v in state['branches'].items() if key in active_keys and v.get('active_path')}
 protected.update(str((run/p).parent.parent.resolve()) for p in state.get('last_candidates',{}).values())
 if state.get('pending'):protected.add(str((run/state['pending']['branch']).resolve()))
 paths=sorted((run/'branches').glob('*/*/*/checkpoints'),key=lambda p:p.stat().st_mtime,reverse=True)
 for index,path in enumerate(paths):
  if index<4 or str(path.parent.resolve()) in protected or path.is_symlink():continue
  if path.resolve().is_relative_to((run/'branches').resolve()):
   shutil.rmtree(path)
   versions=path.parent/'policy_versions'
   if versions.is_dir() and not versions.is_symlink():shutil.rmtree(versions)


def train(m,name='research02',choice='auto',wandb='online',once=False,hours=None,config=None):
 from filelock import FileLock
 from nova.tracking import Tracker
 run=create(m,name,choice,config);cfg=m.read(run/'lab.json')
 if m.sha(run/'lab.json')!=m.read(run/'lab_provenance.json')['config_sha256']:raise ValueError('Research configuration changed. Use a new experiment name.')
 # Reject an old binary instead of silently running the old data-dropping loop.
 import subprocess
 subprocess.run([str(m.binary()),'--research-selftest'],env=m.environment(),check=True)
 if cfg['version']=='reward-lab-v2':
  probe=subprocess.run([str(m.binary()),'--evaluation-protocol'],env=m.environment(),capture_output=True,text=True)
  if probe.returncode or probe.stdout.strip()!='arena-rng-v3':raise RuntimeError('Install the paired-evaluation update native executable before resuming research02. Models were preserved.')
 with FileLock(str(run/'train.lock'),timeout=0):
  (run/'STOP').unlink(missing_ok=True);state=m.read(run/'lab_state.json');state['device']=m.device(choice)
  state.pop('error',None)
  from research_pacing import configure
  cfg=configure(m,run,state,cfg);persist(m,run,state)
  tracker=Tracker(run,dict(m.read(run/'config.json'),research=cfg),mode=wandb,continuous=not once)
  tracker.log({},state['total_decisions']);tracker.save_status()
  start_time=time.monotonic();limit=(hours if hours is not None else cfg['default_hours'])*3600
  m.write(m.ROOT/'active_research.json',dict(run=name))
  try:
   while not (run/'STOP').exists() and time.monotonic()-start_time<limit:
    pending=state.get('pending')
    state['status']='training'
    if not pending:
     family=('chronos','galactus')[state['trial']%2]
     population=state.setdefault('population',{}).setdefault(family,copy.deepcopy(cfg['arms']))
     if cfg.get('profile_schedule')=='training-focus-v1':
      from research_pacing import choose
      arm=choose(state,family,population,choose_arm)
     else:arm=choose_arm(state,family,population)
     key=family+'/'+arm['name']
     revision=state['branches'].get(key,dict(restart=0));anchor=m.retained(run,family)
     branch=run/'branches'/family/arm['name']/(m.sha(anchor/'POLICY.lt')[:12]+'_'+str(revision['restart']))
     state['branches'].setdefault(key,dict(restart=0))['active_path']=str(branch.relative_to(run))
     latest=latest_in(branch);native_start=int(latest.name) if latest else 0
     rng=random.Random(cfg['seed']+state['trial']);entries=pool(m,run,state,family)
     opponent=None if state['trial']%5==4 else choose_opponent(entries,state['payoff'].get(family,{}),rng)
     pending=dict(family=family,arm=arm,key=key,branch=str(branch.relative_to(run)),anchor=str(anchor.relative_to(run)),
      start=native_start,target=min(native_start+cfg['block'],cfg['max_branch_decisions']),accounted=native_start,phase='train',opponent=opponent)
     state['pending']=pending;persist(m,run,state)
    family=pending['family'];arm=pending['arm'];branch=run/pending['branch'];branch.mkdir(parents=True,exist_ok=True)
    current=latest_in(branch)
    if pending['phase']=='train':
     settings=m.read(run/'config.json');settings['device']=state['device'];settings['rollout']=cfg['rollout']
     recipe=m.base_recipe(run,family,settings,mode='self',stop_at=pending['target'])
     recipe.update(fixed_rollout=True,checkpoints=str(branch/'checkpoints'),anchor=str(run/pending['anchor']),
      actor_lr=arm['lr']*(.5**min(2,state['branches'].get(pending['key'],{}).get('restart',0))),
      potential_weights=arm['potential'],freeze_shared=arm['freeze_shared'],anchor_coef=arm['anchor'],
      metrics_file=str(branch/'metrics.jsonl'),seed=cfg['seed']+state['trial']*100003)
     if pending['opponent']:recipe['opponent']=pending['opponent']
     m.write(branch/'recipe.json',recipe)
     tracker.log({f'research/{family}/actor_lr':recipe['actor_lr'],f'research/{family}/anchor_coefficient':arm['anchor'],
      f'research/{family}/freeze_shared':float(arm['freeze_shared']),
      **{f'research/{family}/potential_{key}':value for key,value in zip(('field','distance','shot','defense','possession'),arm['potential'])}},state['total_decisions'])
     if current:
      if not (current/'native.json').exists():m.seal_generation(current,family)
      m.verify_generation(current)
      for file in ('POLICY_OPTIM.lt','SHARED_HEAD_OPTIM.lt','CRITIC_OPTIM.lt','CRITIC.lt','RUNNING_STATS.json'):
       if not (current/file).is_file():raise RuntimeError('Incomplete branch checkpoint: '+file)
     old_rows=m.read(branch/'progress.json').get('logged_rows',0) if (branch/'progress.json').exists() else 0
     started=time.monotonic();ran_native=current is None or int(current.name)<pending['target']
     if ran_native:m.launch(recipe)
     elapsed=time.monotonic()-started;current=latest_in(branch)
     if current is None:raise RuntimeError('Research trainer produced no complete checkpoint')
     m.seal_generation(current,family);amount=int(current.name)-pending['accounted'];state['total_decisions']+=amount;pending['accounted']=int(current.name)
     rows=[json.loads(x) for x in (branch/'metrics.jsonl').read_text().splitlines()];new=rows[old_rows:]
     for r in new:
      tracker.log({family+'/'+k:v for k,v in r.items() if isinstance(v,(float,int))},state['total_decisions']-amount+max(0,int(r['Total Timesteps'])-(int(current.name)-amount)))
     m.write(branch/'progress.json',dict(logged_rows=len(rows)))
     speed={f'throughput/{family}/end_to_end_samples_per_second':amount/max(elapsed,1e-6)} if ran_native else {}
     if new:
      tracker.log({**speed,f'learning/{family}/data_use_fraction':sum(r['Used Timesteps'] for r in new)/max(1,sum(r['Collected Timesteps'] for r in new))},state['total_decisions'])
     tracker.save_status()
     pending['anchor_halt']=any(r.get('Guard Halt') for r in new)
     pending['phase']='evaluate' if int(current.name)>=pending['target'] or pending['anchor_halt'] else 'train'
     state.setdefault('last_candidates',{})[family]=str(current.relative_to(run));persist(m,run,state)
     if (run/'STOP').exists():break
     if pending['phase']=='train':continue
    state['status']='evaluating';persist(m,run,state)
    if pending.get('anchor_halt'):
     result=dict(decision='anchor_limit',statistics=dict(delta=None,reason='Frozen-anchor KL limit; no WDL measured'));retire=True
    else:
     result=evaluate(m,run,state,family,current,'development',cfg,tracker)
     if cfg['version']=='reward-lab-v2':
      preserve_promising(m,run,state,family,current,result);persist(m,run,state)
     # Confirm both improvements and apparent regressions on fresh seeds.
     screen=result['decision']
     if screen in ('promising','improved','regressed'):
      if cfg['version']=='reward-lab-v2' and 'confirmation_index' not in pending:
       state['confirmations']=state.get('confirmations',0)+1;pending['confirmation_index']=state['confirmations'];persist(m,run,state)
      result=evaluate(m,run,state,family,current,'confirmation',cfg,tracker)
      if result['decision']=='improved' and screen not in ('promising','improved'):result['decision']='uncertain'
     retire=result['decision']=='regressed'
     for row in result['trials']:
      item=state['payoff'].setdefault(family,{}).setdefault(row['opponent'],dict(points=0,games=0))
      item['points']+=(row['outcome']+1)/2;item['games']+=1
    promoted=result['decision']=='improved'
    if promoted:
     protect(m,run,state,family,current,result)
     print('RESEARCH_PROMOTED:',family,'fresh confirmation passed',flush=True)
    entry=state['arms'].setdefault(pending['key'],dict(n=0,score=0));entry['n']+=1;entry['score']+=(result['statistics']['delta'] if result['statistics']['delta'] is not None else -.5) # Search penalty, never a fabricated WDL measurement.
    if retire or int(current.name)>=cfg['max_branch_decisions']:
     record=state['branches'].setdefault(pending['key'],dict(restart=0));record['restart']+=1
     print('RESEARCH_BRANCH_RETIRED:',family,arm['name'],'champion preserved; next trial continues automatically.',flush=True)
    if promoted:
     state['arms']={k:v for k,v in state['arms'].items() if not k.startswith(family+'/')}
     state['payoff'][family]={}
    tracker.log({f'evaluation/{family}/promoted':float(promoted)},state['total_decisions'])
    tracker.save_status()
    state['results'].append(dict(trial=state['trial'],family=family,arm=arm['name'],decision=result['decision'],statistics=result['statistics'],candidate=str(current.relative_to(run))))
    state['trial']+=1;state['pending']=None;state['status']='training'
    if state['trial']%8==0:evolve(state,cfg)
    prune_branches(m,run,state)
    persist(m,run,state)
    m.report(name)
    if once:break
   state['status']='paused' if (run/'STOP').exists() else 'budget_complete'
  except KeyboardInterrupt:
   (run/'STOP').touch();state['status']='paused'
  except Exception as error:
   state['error']=dict(type=type(error).__name__,message=str(error)[:2000])
   if (run/'STOP').exists():state['status']='paused';print('RESEARCH_PAUSED: evaluation interrupted; saved checkpoint retained.',flush=True)
   else:state['status']='error';raise
  finally:
   persist(m,run,state);tracker.finish(state['status']);m.report(name)
