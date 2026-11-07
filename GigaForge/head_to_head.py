"""Frozen, resumable direct W/D/L: no learning, baseline copies or promotion."""
from pathlib import Path
from types import SimpleNamespace
import csv,hashlib,json,math,subprocess,time


def validate(rows,pairs,seed,seconds,family):
 expected={(seed+p,s) for p in range(pairs) for s in (0,1)}
 if len(rows)!=2*pairs or {(r['seed'],r['side']) for r in rows}!=expected:raise ValueError('Wrong or duplicate head-to-head round count')
 for r in rows:
  if r['opponent']!='original_'+family or abs(r['seconds']-seconds)>1e-6:raise ValueError('Wrong opponent or timeout')
  a,b=r['goals_for'],r['goals_against']
  if any(type(x) is not int or x<0 for x in (a,b)) or r['outcome']!=((a>b)-(a<b)):raise ValueError('Invalid W/D/L outcome')


def summary(rows):
 from scipy.stats import t
 wins=sum(r['outcome']==1 for r in rows);draws=sum(r['outcome']==0 for r in rows);losses=len(rows)-wins-draws
 score=(wins+.5*draws)/len(rows) if rows else None
 blocks={}
 for r in rows:blocks.setdefault(r['seed'],[]).append((r['outcome']+1)/2)
 paired=[sum(v)/2 for v in blocks.values() if len(v)==2]
 lower=upper=None
 if len(paired)>=2:
  mean=sum(paired)/len(paired);variance=sum((v-mean)**2 for v in paired)/(len(paired)-1)
  margin=float(t.ppf(.975,len(paired)-1))*math.sqrt(variance/len(paired)) if variance>0 else math.sqrt(math.log(40)/(2*len(paired)))
  lower=max(0.,mean-margin);upper=min(1.,mean+margin)
 verdict='uncertain'
 if lower is not None and lower>.5:verdict='candidate_ahead_in_this_test'
 elif upper is not None and upper<.5:verdict='original_ahead_in_this_test'
 return dict(games=len(rows),wins=wins,draws=draws,losses=losses,score_rate=score,
  goals_for=sum(r['goals_for'] for r in rows),goals_against=sum(r['goals_against'] for r in rows),
  score_interval_95=[lower,upper],verdict=verdict,
  interval_method='Approximate paired-seed Student-t interval; both colors form one block. Zero sample variance uses a bounded Hoeffding interval. No automatic promotion.')


def select(m,run):
 import trial_watch
 from research_eval import digest
 state=m.read(run/'lab_state.json');ranked=[];seen=set();attempts=[]
 for r in state.get('results',[]):
  if r['family'] not in ('chronos','galactus'):continue
  path=run/'evaluations'/f'lab_{r["trial"]:05d}_{r["family"]}_confirmation.json'
  if not path.is_file():continue
  result=m.read(path)
  if result['statistics']['delta']>0:ranked.append((result['statistics']['delta'],r))
 if not ranked:raise FileNotFoundError('No positive confirmation-test candidate recorded; no original or latest model substituted')
 # Memoize file hashes while holding the run lock; no repeated disk-wide reads.
 hashes={}
 def cached_sha(path):
  p=Path(path);stat=p.stat();key=(str(p.resolve()),stat.st_size,stat.st_mtime_ns)
  if key not in hashes:hashes[key]=m.sha(p)
  return hashes[key]
 proxy=SimpleNamespace(**vars(m));proxy.sha=cached_sha
 for delta,r in sorted(ranked,key=lambda v:(v[0],v[1]['trial']),reverse=True):
  try:target=trial_watch.trial_identity(proxy,run,r['family'],r['trial'])
  except (OSError,ValueError,KeyError) as error:
   attempts.append(dict(trial=r['trial'],family=r['family'],lookup='identity_unavailable',error=str(error)));continue
  tag=digest(target['files'])
  if tag in seen:continue
  seen.add(tag);found=trial_watch.find_exact(proxy,run,target)
  attempts.append(dict(trial=r['trial'],family=r['family'],confirmation_delta=delta,lookup=found['kind']))
  if found['kind']=='missing':continue
  actor=trial_watch.prepare(proxy,run,r['family'],r['trial'])
  return dict(trial=r['trial'],family=r['family'],confirmation_delta=delta,files=target['files'],actor=str(actor),attempts=attempts)
 m.write(run/'h2h_selection.json',dict(status='no_weights_available',attempts=attempts))
 raise FileNotFoundError('No positive confirmation-test candidate weights found; see h2h_selection.json')


def native_actor(m,run,selection,settings,test):
 """Use saved native components, or materialize a verified native-only export."""
 import torch
 from nova.giga_teachers import GigaNetwork
 from trial_watch import FILES
 actor=Path(selection['actor']);pin=actor.parent;family=selection['family']
 script=torch.jit.load(str(actor),map_location='cpu').eval()
 if not all((pin/n).is_file() for n in FILES):
  weights=script.state_dict()
  if any(k not in weights or torch.count_nonzero(weights[k]).item()!=0 for k in ('residual.2.weight','residual.2.bias')):
   raise ValueError('Export has non-core policy changes; cannot convert it to the exact native actor')
  pin=test/'native_candidate';pin.mkdir(parents=True,exist_ok=True)
  torch.jit.save(script.core.head,str(pin/'SHARED_HEAD.lt'));torch.jit.save(script.core.policy,str(pin/'POLICY.lt'))
  m.seal_generation(pin,family)
 # Test both native archive loading and actual logits before a long tournament.
 size=225 if family=='chronos' else 258
 x=torch.linspace(-1,1,4*(size+3)).reshape(4,size+3)
 with torch.inference_mode():
  expected=script(x);torch.testing.assert_close(GigaNetwork(pin,family)(x[:,:size]),expected,rtol=0,atol=0)
 out=test/'native_logits.json';recipe=m.base_recipe(run,family,settings,mode='self')
 recipe.update(anchor=str(pin),checkpoints='',games=2,probe_only=True,probe_input=x[:,:size].contiguous().flatten().tolist(),probe_output=str(out),stop_file=str(test/'STOP'),metrics_file=str(test/'unused_metrics.jsonl'))
 m.launch(recipe,log=test/'native_parity.log')
 torch.testing.assert_close(torch.tensor(m.read(out)).reshape(4,90),expected,rtol=3e-5,atol=5e-5)
 return pin


def run(m,name='research02',choice='auto',rounds=200,seconds=100.,batch_pairs=25,seed=1580000000):
 from filelock import FileLock
 from research_eval import digest
 from trial_watch import identity
 if rounds<2 or rounds%2 or seconds<=0 or seconds*15!=round(seconds*15) or batch_pairs<1:raise ValueError('Use an even game count, positive duration aligned to 1/15s, and positive batch size')
 if not 0<=seed<=2_000_000_000-rounds:raise ValueError('Seed outside the supported range')
 run=m.folder(name)
 if not (run/'lab_state.json').is_file():raise FileNotFoundError('Head-to-head testing requires an existing research run')
 test_root=run/'h2h';test_root.mkdir(parents=True,exist_ok=True)
 with FileLock(str(run/'train.lock'),timeout=0),FileLock(str(test_root/'test.lock'),timeout=0):
  probe=subprocess.run([str(m.binary()),'--head-to-head-protocol'],env=m.environment(),capture_output=True,text=True)
  if probe.returncode or probe.stdout.strip()!='direct-h2h-v1':raise RuntimeError('Install the complete 200-round test update, including native/GigaForge.exe')
  settings=m.read(run/'config.json');settings['device']=m.device(choice)
  request=dict(rounds=rounds,seconds=seconds,batch_pairs=batch_pairs,seed=seed)
  pointer=test_root/'active.json'
  if pointer.exists() and m.read(pointer).get('request')==request:
   test=(test_root/m.read(pointer)['directory']).resolve()
   if not test.is_relative_to(test_root.resolve()):raise ValueError('Invalid test path')
   state=m.read(test/'test.json')
   if state['binary_sha256']!=m.sha(m.binary()):raise ValueError('Native executable changed during this test. Keep the existing results and use a different --seed for a new test.')
  else:
   selection=select(m,run);family=selection['family']
   key=digest(dict(selection=selection['files'],family=family,request=request,binary=m.sha(m.binary())))[:16]
   test=test_root/key;test.mkdir(exist_ok=True)
   from nova.teachers import verify_teacher
   original=verify_teacher(family)
   import shutil
   original_pin=test/'original';original_pin.mkdir(exist_ok=True)
   for file in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(original/file,original_pin/file)
   m.seal_generation(original_pin,family)
   candidate=native_actor(m,run,selection,settings,test)
   state=dict(status='ready',selection=selection,request=request,family=family,candidate=str(candidate),original=str(original_pin),
    candidate_files=identity(m,candidate),original_files=identity(m,original_pin),binary_sha256=m.sha(m.binary()),
    device=settings['device'],actor_sha256=m.sha(selection['actor']),chunks=[],games=[],automatic_promotion=False)
   m.write(test/'test.json',state);m.write(pointer,dict(directory=test.name,request=request))
  stop=test/'STOP';stop.unlink(missing_ok=True)
  family=state['family'];settings['device']=state['device'];started=time.monotonic()
  print(f'H2H_SELECTED: {family} trial {state["selection"]["trial"]}, prior confirmation difference {state["selection"]["confirmation_delta"]:+.2%}. Unverified candidate.',flush=True)
  print(f'H2H_TEST: {rounds} unique games, {seconds:g} simulated seconds each, {rounds//2} games per color. Draw at timeout; no overtime. No training or extra baseline games.',flush=True)
  print('H2H_OUTPUT:',test,flush=True)
  try:
   state['status']='running'
   for offset in range(0,rounds//2,batch_pairs):
    pairs=min(batch_pairs,rounds//2-offset);output=test/f'batch_{offset:04d}.json'
    if identity(m,Path(state['candidate']))!=state['candidate_files'] or identity(m,Path(state['original']))!=state['original_files']:raise ValueError('Frozen test weights changed')
    if stop.exists():break
    if output.exists():data=m.read(output)
    else:
     spec=dict(candidate=m.descriptor(state['candidate'],family),opponents=[dict(m.descriptor(state['original'],family),name='original_'+family)],
      compare_baseline=False,pairs=pairs,seconds=seconds,seed=seed+offset,output=str(output),stop_file=str(stop))
     recipe=m.base_recipe(run,family,settings,mode='self');recipe.update(evaluation=spec,stop_file=str(stop))
     print(f'H2H_BATCH: games {2*offset+1}-{2*(offset+pairs)}/{rounds}',flush=True)
     m.launch(recipe,log=test/f'batch_{offset:04d}.log');data=m.read(output)
    if not data.get('direct_head_to_head') or data['baseline_trials']:raise ValueError('Native engine ran unwanted baseline copies')
    validate(data['trials'],pairs,seed+offset,seconds,family)
    # Rebuild from completed batches; resuming never double-counts games.
    known={c['offset']:c for c in state['chunks']};known[offset]=dict(offset=offset,path=output.name,sha256=m.sha(output))
    state['chunks']=[known[k] for k in sorted(known)];games=[]
    for chunk in state['chunks']:
     path=test/chunk['path']
     if m.sha(path)!=chunk['sha256']:raise ValueError('Completed W/D/L batch changed')
     games.extend(m.read(path)['trials'])
    state['games']=games;state['summary']=summary(games)
    state['by_side']={('blue' if side==0 else 'orange'):summary([r for r in games if r['side']==side]) for side in (0,1)}
    m.write(test/'test.json',state)
    s=state['summary'];print(f'H2H_PROGRESS: {s["games"]}/{rounds}: {s["wins"]} W / {s["draws"]} D / {s["losses"]} L; goals {s["goals_for"]}:{s["goals_against"]}',flush=True)
   state['status']='complete' if len(state['games'])==rounds else 'paused'
  except KeyboardInterrupt:stop.touch();state['status']='paused'
  except Exception as error:
   state['status']='paused' if stop.exists() else 'error';state['error']=str(error)
   if state['status']=='error':raise
  finally:
   state['invocation_seconds']=time.monotonic()-started;m.write(test/'test.json',state)
   if state['games']:
    with (test/'games.csv').open('w',newline='',encoding='utf8') as out:
     writer=csv.DictWriter(out,fieldnames=['round','seed','side','opponent','goals_for','goals_against','outcome','seconds']);writer.writeheader()
     for i,row in enumerate(state['games'],1):writer.writerow(dict(round=i,**{k:row[k] for k in writer.fieldnames if k!='round'}))
   m.write(run/'latest_h2h.json',state)
  print('H2H_RESULT:',state['status'],state.get('summary',{}),flush=True)
  return state
