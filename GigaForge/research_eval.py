"""Fixed-budget paired evaluations with bounded batches and resumable results.

Only complete, fingerprint-matching native jobs are reused. No early stopping
on a favorable confidence interval, or repeated analysis within a stage.
"""
from __future__ import annotations
import hashlib,json,math,time
from pathlib import Path


def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def model_identity(m,descriptor):
 path=Path(descriptor['path'])
 return dict(family=descriptor['family'],hitbox=descriptor['hitbox'],
  files={n:m.sha(path/n) for n in ('SHARED_HEAD.lt','POLICY.lt')})


def validate(result,spec):
 if result.get('evaluation_protocol')!='arena-rng-v3':raise ValueError('Update the native executable: evaluation requires arena-rng-v3')
 expected={(o['name'],spec['seed']+i*10000+p,s) for i,o in enumerate(spec['opponents'])
  for p in range(spec['pairs']) for s in (0,1)}
 for key in ('trials','baseline_trials'):
  rows=result[key]
  if len(rows)!=len(expected) or {(r['opponent'],r['seed'],r['side']) for r in rows}!=expected:
   raise ValueError('Incomplete or unpaired native evaluation')
  for row in rows:
   a,b=row['goals_for'],row['goals_against']
   if any(type(x) is not int or x<0 for x in (a,b)) or row['outcome']!=((a>b)-(a<b)):
    raise ValueError('Invalid evaluation outcome')
   if not math.isclose(row['seconds'],round(spec['seconds']*15)/15,abs_tol=1e-6):
    raise ValueError('Evaluation duration mismatch')


def interval(rows,baseline,metric='score',alpha=.05):
 """Fixed opponent strata, paired seeds, with both colors in each block."""
 from scipy.stats import t
 import numpy as np
 if not 0<alpha<1:raise ValueError('Invalid confidence level')
 key=lambda r:(r['opponent'],r['seed'],r['side'])
 old={key(r):r for r in baseline}
 if len(old)!=len(baseline) or len(rows)!=len(old) or len({key(r) for r in rows})!=len(rows):
  raise ValueError('Unpaired evaluation rows')
 def value(r):
  if metric=='score':return (r['outcome']+1)/2
  rate=60/r['seconds']
  if metric=='attack':return r['goals_for']*rate
  if metric=='defense':return -r['goals_against']*rate
  if metric=='goal_difference':return (r['goals_for']-r['goals_against'])*rate
  raise ValueError('Unknown evaluation metric')
 blocks={}
 for row in rows:
  blocks.setdefault((row['opponent'],row['seed']),[]).append(value(row)-value(old[key(row)]))
 if not blocks or any(len(v)!=2 for v in blocks.values()):raise ValueError('Each seed needs both colors')
 strata={}
 for (opponent,_),values in blocks.items():strata.setdefault(opponent,[]).append(sum(values)/2)
 means={k:float(np.mean(v)) for k,v in strata.items()};delta=sum(means.values())/len(means)
 df=min(map(len,strata.values()))-1
 se=math.sqrt(sum(float(np.var(v,ddof=1))/len(v) for v in strata.values()))/len(strata) if df>=3 else None
 margin=max(1e-6,float(t.ppf(1-alpha/2,df))*se) if se is not None else None
 return dict(delta=delta,lower=None if margin is None else delta-margin,upper=None if margin is None else delta+margin,
  standard_error=se,blocks=len(blocks),by_opponent=means,alpha=alpha,
  caution='Approximate paired Student-t interval on this simulator opponent panel; not a guarantee of live strength.')


def assess(rows,baseline,cfg,split,confirmation_index=1):
 # Summable confirmation error budgets reduce false discoveries across an
 # adaptive search. Every guard must pass (an intersection-union decision).
 alpha=cfg.get('confirmation_error_budget',.05)/(confirmation_index*(confirmation_index+1)) if split!='development' else .05
 metrics={k:interval(rows,baseline,k,alpha) for k in ('score','attack','defense','goal_difference')}
 opponents=sorted({r['opponent'] for r in rows})
 per={o:interval([r for r in rows if r['opponent']==o],[r for r in baseline if r['opponent']==o],alpha=alpha) for o in opponents}
 score=metrics['score'];decision='uncertain'
 if score['lower'] is not None:
  if split=='development':
   if score['upper']<0:decision='regressed'
   elif score['delta']>=cfg['minimum_delta']:decision='promising'
  elif score['upper']<0:decision='regressed'
  elif (score['lower']>0 and score['delta']>=cfg['minimum_delta']
   and all(v['lower']>=-cfg['opponent_tolerance'] for v in per.values())
   and all(metrics[k]['lower']>=-cfg['goal_rate_tolerance'] for k in ('attack','defense','goal_difference'))):
   decision='improved'
 return dict(statistics=score,metrics=metrics,per_opponent_statistics=per,decision=decision,
  confirmation_index=confirmation_index if split!='development' else None,
  promotion_scope='Paired match score improves; per-opponent score, scoring and conceding pass configured noninferiority checks. No mechanics or live RLBot strength claim.')


def native_jobs(m,run,state,family,candidate,baseline,panel,split,cfg):
 """Completed batches survive pause/restart; no mixing different checkpoints."""
 settings=m.read(run/'config.json');settings['device']=state['device']
 recipe=m.base_recipe(run,family,settings,mode='self')
 import torch
 meshes=Path(recipe['meshes']) if 'meshes' in recipe else None
 total=cfg['development_pairs'] if split=='development' else cfg['confirmation_pairs']
 chunk=cfg.get('evaluation_batch_pairs',32)
 if total<1 or chunk<1 or total>=10000:raise ValueError('Invalid evaluation seed budget')
 base=(410000000 if split=='development' else 710000000)+state['trial']*10000
 if split=='initial_confirmation':base+=1000000000
 root=run/'evaluations'/'jobs';root.mkdir(parents=True,exist_ok=True)
 identity=dict(protocol='fixed-evaluation-v3',binary=m.sha(m.binary()),device=recipe['device'],
  torch_version=torch.__version__,cuda_runtime=torch.version.cuda,
  meshes={p.relative_to(meshes).as_posix():m.sha(p) for p in sorted(meshes.rglob('*')) if p.is_file()} if meshes else {},
  torch_threads=recipe['torch_threads'],simulation_threads=recipe['simulation_threads'],
  controller=m.sha(Path(__file__)),models=[model_identity(m,d) for d in (m.descriptor(candidate,family),m.descriptor(baseline,family),*panel)])
 result=dict(trials=[],baseline_trials=[],wall_seconds=0.,player_decisions=0,batches=0,reused_batches=0)
 started=time.monotonic()
 for offset in range(0,total,chunk):
  if (run/'STOP').exists():raise RuntimeError('Evaluation paused')
  spec=dict(candidate=m.descriptor(candidate,family),baseline=m.descriptor(baseline,family),opponents=panel,
   pairs=min(chunk,total-offset),seconds=cfg['seconds'],seed=base+offset,stop_file=str(run/'STOP'))
  fingerprint=digest(dict(identity=identity,pairs=spec['pairs'],seconds=spec['seconds'],seed=spec['seed'],opponents=[d['name'] for d in panel]))
  cache=root/(fingerprint+'.json');raw=root/(fingerprint+'.native.json');log=root/(fingerprint+'.log')
  cached=m.read(cache) if cache.exists() else None
  if cached is not None:
   if cached['fingerprint']!=fingerprint or digest(cached['result'])!=cached['result_sha256']:raise ValueError('Evaluation cache changed')
   batch=cached['result'];validate(batch,spec);result['reused_batches']+=1
  else:
   spec['output']=str(raw);job=dict(recipe,evaluation=spec)
   print(f'RESEARCH_EVAL {family} {split}: seeds {offset+1}-{offset+spec["pairs"]}/{total}; {len(panel)*spec["pairs"]*4} games, native progress log {log}',flush=True)
   m.launch(job,log=log);batch=m.read(raw);validate(batch,spec)
   m.write(cache,dict(fingerprint=fingerprint,result_sha256=digest(batch),identity=identity,result=batch));raw.unlink(missing_ok=True)
  for k in ('trials','baseline_trials'):result[k].extend(batch[k])
  for k in ('wall_seconds','player_decisions'):result[k]+=batch[k]
  result['batches']+=1
  print(f'RESEARCH_EVAL_COMPLETE {family} {split}: {offset+spec["pairs"]}/{total} seed pairs per opponent',flush=True)
 result['invocation_wall_seconds']=time.monotonic()-started
 result['scope']='15 decisions/second at native tick-skip 8; timed matches include draws, no overtime. Original feature contracts and hitboxes.'
 return result


def evaluate(m,run,state,family,candidate,split,cfg,tracker):
 from nova.forge_eval import summary
 panel=[dict(m.descriptor(run/'parents'/f,f),name='original_'+f) for f in ('chronos','galactus')]
 other='galactus' if family=='chronos' else 'chronos';current_other=m.retained(run,other)
 if current_other!=(run/'parents'/other).resolve():panel.append(dict(m.descriptor(current_other,other),name='accepted_'+other+'_'+m.sha(current_other/'POLICY.lt')[:8]))
 baseline=m.retained(run,family)
 result=native_jobs(m,run,state,family,candidate,baseline,panel,split,cfg)
 result.update(family=family,split=split,summary=summary(result['trials']),baseline_summary=summary(result['baseline_trials']))
 result.update(assess(result['trials'],result['baseline_trials'],cfg,split,state.get('pending',{}).get('confirmation_index',1)))
 if split=='confirmation' and result['decision']=='improved' and baseline!=(run/'parents'/family).resolve():
  initial=native_jobs(m,run,state,family,candidate,run/'parents'/family,panel,'initial_confirmation',cfg)
  initial.update(assess(initial['trials'],initial['baseline_trials'],cfg,'initial_confirmation',state['pending']['confirmation_index']))
  result['against_initial']=initial
  if initial['decision']!='improved':result['decision']='uncertain'
 output=run/'evaluations'/f'lab_{state["trial"]:05d}_{family}_{split}.json';m.write(output,result)
 prefix=f'evaluation/{family}/{split}'
 log={prefix+'/candidate_score':result['summary']['score_rate'],prefix+'/baseline_score':result['baseline_summary']['score_rate'],
  prefix+'/games_per_actor':result['summary']['matches'],prefix+'/native_seconds':result['wall_seconds'],prefix+'/reused_batches':result['reused_batches']}
 for metric,values in result['metrics'].items():
  for key in ('delta','lower','upper'):
   if values[key] is not None:log[prefix+'/'+metric+'/'+key]=values[key]
 tracker.log(log,state['total_decisions'])
 print('RESEARCH_WDL',family,split,result['summary'],'baseline',result['baseline_summary'],result['decision'],flush=True)
 return result
