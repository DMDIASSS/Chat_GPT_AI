"""Locate a tested actor by evaluation identity; never substitute another actor."""
from pathlib import Path
import hashlib,json,os,shutil,time

FILES=('SHARED_HEAD.lt','POLICY.lt')


def local_path(run,value):
 path=(run/Path(str(value).replace('\\','/'))).resolve()
 if not path.is_relative_to(run.resolve()):raise ValueError('Trial path leaves the selected run')
 return path


def identity(m,path):return {n:m.sha(Path(path)/n) for n in FILES}


def trial_identity(m,run,family,trial):
 state=m.read(run/'lab_state.json')
 records=[r for r in state.get('results',[]) if r['trial']==trial and r['family']==family]
 if len(records)!=1:raise ValueError(f'No completed {family} trial {trial} in {run.name}')
 record=records[0]
 path=run/'evaluations'/f'lab_{trial:05d}_{family}_confirmation.json'
 if not path.is_file():path=path.with_name(f'lab_{trial:05d}_{family}_development.json')
 evaluation=m.read(path)
 key=lambda r:(r['opponent'],r['seed'],r['side'])
 target={key(r):r for r in evaluation['trials']};covered=set();identities={}
 for job in sorted((run/'evaluations/jobs').glob('*.json')):
  if job.name.endswith('.native.json'):continue
  data=m.read(job);rows=data.get('result',{}).get('trials',[])
  if not rows or not all(key(r) in target and r==target[key(r)] for r in rows):continue
  candidate=data.get('identity',{}).get('models',[{}])[0]
  if candidate.get('family')!=family or candidate.get('hitbox')!=('breakout' if family=='chronos' else 'octane'):continue
  files=candidate.get('files',{})
  if set(files)!=set(FILES):continue
  identities[tuple(files[n] for n in FILES)]=files;covered.update(key(r) for r in rows)
 if len(identities)!=1 or covered!=set(target):
  raise ValueError('Exact model identity is missing or ambiguous in the evaluation jobs; no actor selected')
 return dict(record=record,evaluation=str(path.relative_to(run)),family=family,trial=trial,
  split=evaluation['split'],delta=evaluation['statistics']['delta'],files=next(iter(identities.values())))


def walk_files(roots,name,deadline,limit=5000):
 count=0
 for root in roots:
  if not root.is_dir():continue
  for directory,dirs,files in os.walk(root,followlinks=False):
   dirs[:]=[n for n in dirs if not (Path(directory)/n).is_symlink()
    and not getattr((Path(directory)/n).lstat(),'st_file_attributes',0)&0x400]
   count+=1
   if count>limit or time.monotonic()>deadline:return
   for file in files:
    if file==name or (name=='*.lt' and file.endswith('.lt')):yield Path(directory)/file


def find_exact(m,run,target,seconds=45):
 expected=target['files'];family=target['family'];checked=[];errors=[];deadline=time.monotonic()+seconds
 preferred=local_path(run,target['record']['candidate'])
 roots=[run/'branches',run/'shortlist',run/'tested_candidates',run/'watch_pins',run/'champions',run/'parents']
 def candidates():
  yield preferred
  for path in walk_files(roots,'POLICY.lt',deadline):yield path.parent
 seen=set()
 for directory in candidates():
  directory=directory.resolve()
  if directory in seen:continue
  seen.add(directory)
  if not all((directory/n).is_file() for n in FILES):continue
  checked.append(str(directory))
  try:
   if m.sha(directory/'POLICY.lt')==expected['POLICY.lt'] and m.sha(directory/'SHARED_HEAD.lt')==expected['SHARED_HEAD.lt']:
    return dict(kind='native',path=str(directory),checked=len(checked),errors=errors)
  except OSError as error:errors.append(dict(path=str(directory),error=type(error).__name__))
  if time.monotonic()>deadline:break
 exports=[run/'export_actors'/family,run/'watch_pins',m.ROOT/'exports'/run.name,m.ROOT/'views'/run.name]
 for actor in walk_files(exports,'*.lt',time.monotonic()+15):
  sidecar=Path(str(actor)+'.json')
  if not sidecar.is_file():continue
  try:
   meta=m.read(sidecar)
   if meta.get('contract',{}).get('family')!=family or meta['contract'].get('hitbox')!=('breakout' if family=='chronos' else 'octane'):continue
   source=meta.get('source_native',{}).get('files',{})
   if all(source.get(n)==expected[n] for n in FILES):
    from nova.forge_models import check_actor
    check_actor(actor,family)
    return dict(kind='export',path=str(actor),checked=len(checked),errors=errors)
  except (OSError,ValueError,KeyError) as error:errors.append(dict(path=str(actor),error=type(error).__name__))
 return dict(kind='missing',checked=len(checked),errors=errors,search_seconds=seconds,
  reason='No matching actor files found in saved checkpoints, policy versions, shortlist, pinned actors or this run\'s exports. No substitute selected.')


def prepare(m,run,family,trial):
 lookup=run/'watch_requests'/f'trial_{trial:05d}_{family}.json'
 try:target=trial_identity(m,run,family,trial)
 except (OSError,ValueError,KeyError) as error:
  m.write(lookup,dict(status='identity_unavailable',trial=trial,family=family,error=str(error)))
  raise
 print(f'EXACT_TRIAL_WATCH: {family} trial {trial}, {target["split"]} match-score difference {target["delta"]:+.2%}; unverified candidate.',flush=True)
 print('Locating both recorded model-file hashes; training and champion pointers stay unchanged.',flush=True)
 found=find_exact(m,run,target)
 m.write(lookup,dict(target=target,lookup=found))
 if found['kind']=='missing':
  raise FileNotFoundError(f'Trial {trial} weights were not found. Checkpoint rotation may have removed them. The score/report cannot reconstruct weights. No other bot was opened. Lookup report: {lookup}')
 import torch
 from nova.giga_teachers import GigaNetwork
 from nova.forge_models import DirectActor,save_actor,check_actor
 tag=hashlib.sha256(json.dumps(target['files'],sort_keys=True).encode()).hexdigest()
 pin=run/'watch_pins'/family/f'trial_{trial:05d}_{tag[:12]}'
 pin.mkdir(parents=True,exist_ok=True);actor=pin/'actor.lt'
 role=f'trial {trial} candidate (unverified)'
 if not actor.exists():
  if found['kind']=='native':
   source=Path(found['path'])
   if identity(m,source)!=target['files']:raise ValueError('Selected model changed during lookup')
   for name in FILES:shutil.copy2(source/name,pin/name)
   if identity(m,pin)!=target['files']:raise ValueError('Pinned model hash mismatch')
   m.seal_generation(pin,family)
   network=DirectActor(family);network.core.load_state_dict(GigaNetwork(pin,family).state_dict(),strict=True)
   save_actor(network,actor,family,hitbox='breakout' if family=='chronos' else 'octane',
    source_native=m.read(pin/'native.json'),role=role,research_trial=trial,trial_evidence=target)
  else:
   source=Path(found['path']);meta=check_actor(source,family)
   shutil.copy2(source,actor);meta.update(role=role,research_trial=trial,trial_evidence=target)
   m.write(Path(str(actor)+'.json'),meta)
 meta=check_actor(actor,family)
 if any(meta.get('source_native',{}).get('files',{}).get(n)!=target['files'][n] for n in FILES):raise ValueError('Pinned actor provenance mismatch')
 with torch.inference_mode():
  logits=torch.jit.load(str(actor),map_location='cpu')(torch.zeros(2,(225 if family=='chronos' else 258)+3))
  if logits.shape!=(2,90) or not torch.isfinite(logits).all():raise ValueError('Pinned actor failed inference check')
 print('EXACT_TRIAL_FOUND:',found['path'],'pinned:',actor,flush=True)
 return actor
