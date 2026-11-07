"""Synthetic statistical/cache failures, not evidence of playing strength."""
import copy,hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research as r
import research_eval as e


def rows(pairs=32,goals=(1,1)):
 a,b=goals
 return [dict(opponent=o,seed=p,side=s,goals_for=a,goals_against=b,
  outcome=(a>b)-(a<b),seconds=60) for o in ('c','g') for p in range(pairs) for s in (0,1)]


def test_identical_actors_never_promote():
 data=rows();result=e.assess(data,copy.deepcopy(data),r.DEFAULT,'confirmation')
 assert result['decision']=='uncertain' and result['statistics']['lower']<0<result['statistics']['upper']


def test_screen_is_only_promising_and_confirmation_needs_all_guards():
 good=rows(goals=(2,1));old=rows(goals=(1,1))
 assert e.assess(good,old,r.DEFAULT,'development')['decision']=='promising'
 assert e.assess(good,old,r.DEFAULT,'confirmation')['decision']=='improved'
 assert e.assess(rows(goals=(4,2)),old,r.DEFAULT,'confirmation')['decision']=='uncertain' # defense
 assert e.assess(rows(goals=(1,0)),rows(goals=(2,2)),r.DEFAULT,'confirmation')['decision']=='uncertain' # attack


def test_per_opponent_regression_cannot_hide_in_overall_gain():
 old=rows(goals=(0,1));new=rows(goals=(1,0))
 # Make the second stratum worse, with a smaller regression than the first gain.
 for a,b in zip(new,old):
  if a['opponent']=='g':a.update(goals_for=0,goals_against=1,outcome=-1);b.update(goals_for=1,goals_against=1,outcome=0)
 assert e.assess(new,old,r.DEFAULT,'confirmation')['statistics']['delta']>0
 assert e.assess(new,old,r.DEFAULT,'confirmation')['decision']=='uncertain'


def test_confirmation_budget_is_summable_and_more_cautious_over_time():
 a=e.assess(rows(),rows(),r.DEFAULT,'confirmation',1)['statistics']['alpha']
 b=e.assess(rows(),rows(),r.DEFAULT,'confirmation',20)['statistics']['alpha']
 assert a==.025 and b<a
 assert sum(.05/(n*(n+1)) for n in range(1,10000))<.05


def test_unpaired_or_missing_color_data_rejected():
 with pytest.raises(ValueError):e.interval(rows()[:-1],rows())
 data=rows();data[1]=copy.deepcopy(data[0])
 with pytest.raises(ValueError):e.interval(data,rows())


def fake_runner(tmp_path):
 def write(path,value):
  path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
 def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
 def descriptor(path,family):return dict(path=str(path),family=family,hitbox='breakout' if family=='chronos' else 'octane')
 for family in ('chronos','galactus'):
  for n in ('POLICY.lt','SHARED_HEAD.lt'):
   path=tmp_path/'parents'/family/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((family+n).encode())
 write(tmp_path/'config.json',dict(device='cpu'))
 binary=tmp_path/'GigaForge';binary.write_bytes(b'test fixture only')
 m=SimpleNamespace(write=write,read=lambda p:json.loads(Path(p).read_text()),sha=sha,binary=lambda:binary,descriptor=descriptor,
  base_recipe=lambda *a,**kw:dict(device='cpu',torch_threads=1,simulation_threads=2),calls=0,
  seal_generation=lambda *a:None,verify_generation=lambda *a:None)
 def launch(recipe,**kwargs):
  m.calls+=1;spec=recipe['evaluation'];data=[]
  for i,o in enumerate(spec['opponents']):
   for p in range(spec['pairs']):
    for s in (0,1):data.append(dict(opponent=o['name'],seed=spec['seed']+i*10000+p,side=s,seconds=spec['seconds'],goals_for=1,goals_against=1,outcome=0))
  write(spec['output'],dict(evaluation_protocol='arena-rng-v3',trials=data,baseline_trials=copy.deepcopy(data),wall_seconds=1.,player_decisions=2*len(data)*int(15*spec['seconds'])))
 m.launch=launch
 return m


def job_args(tmp_path):
 m=fake_runner(tmp_path)
 panel=[dict(m.descriptor(tmp_path/'parents'/f,f),name=f) for f in ('chronos','galactus')]
 args=(m,tmp_path,dict(device='cpu',trial=0),'chronos',tmp_path/'parents/chronos',tmp_path/'parents/chronos',panel,'development',dict(r.DEFAULT,development_pairs=4,evaluation_batch_pairs=2))
 return m,args


def test_completed_jobs_reused_but_never_mixed_after_weights_change(tmp_path):
 m,args=job_args(tmp_path);a=e.native_jobs(*args);b=e.native_jobs(*args)
 assert m.calls==2 and b['reused_batches']==2 and a['trials']==b['trials'] and len(b['trials'])==16
 (tmp_path/'parents/chronos/POLICY.lt').write_bytes(b'new actor')
 c=e.native_jobs(*args);assert m.calls==4 and c['reused_batches']==0


def test_pause_retains_only_complete_batches_and_resume_finishes_budget(tmp_path):
 m,args=job_args(tmp_path);original=m.launch
 def pause(recipe,**kw):original(recipe,**kw);(tmp_path/'STOP').touch()
 m.launch=pause
 with pytest.raises(RuntimeError):e.native_jobs(*args)
 assert m.calls==1
 (tmp_path/'STOP').unlink();m.launch=original
 data=e.native_jobs(*args)
 assert m.calls==2 and data['reused_batches']==1 and len(data['trials'])==16


def test_corrupt_cache_rejected(tmp_path):
 m,args=job_args(tmp_path);e.native_jobs(*args)
 path=next((tmp_path/'evaluations/jobs').glob('*.json'));value=m.read(path);value['result']['trials'][0]['outcome']=-1;m.write(path,value)
 with pytest.raises(ValueError,match='cache changed'):e.native_jobs(*args)


def test_shortlist_survives_original_deletion_and_stays_bounded(tmp_path):
 import shutil
 m=fake_runner(tmp_path);state=dict(trial=0)
 for i,delta in enumerate((.1,.3,.2,.05)):
  candidate=tmp_path/'temporary';candidate.mkdir(exist_ok=True)
  for n in ('POLICY.lt','SHARED_HEAD.lt'):(candidate/n).write_bytes(str(i).encode())
  r.preserve_promising(m,tmp_path,state,'chronos',candidate,dict(statistics=dict(delta=delta,lower=delta-.2)))
  shutil.rmtree(candidate)
 entries=state['shortlist']['chronos']
 assert len(entries)==2 and [a['statistics']['delta'] for a in entries]==[.3,.2]
 assert all((tmp_path/a['path']/'SHARED_HEAD.lt').is_file() and not a['verified_champion'] for a in entries)


def test_population_waits_for_repeated_measurements():
 state=dict(trial=8,population={'chronos':copy.deepcopy(r.ARMS)},arms={})
 for arm in r.ARMS:state['arms']['chronos/'+arm['name']]=dict(n=1,score=.1)
 r.evolve(state,r.DEFAULT)
 assert state['population']['chronos']==r.ARMS


def test_busy_predecessor_does_not_leave_an_unresumable_new_run(tmp_path):
 from filelock import FileLock
 m=fake_runner(tmp_path);m.folder=lambda n:tmp_path/n
 m.create=lambda *a:pytest.fail('Must not create a study while predecessor is locked')
 m.write(tmp_path/'research01/lab_state.json',dict(status='training'))
 with FileLock(str(tmp_path/'research01/train.lock'),timeout=0):
  with pytest.raises(RuntimeError,match='Pause research01'):r.create(m,'research02')
 assert not (tmp_path/'research02').exists()
