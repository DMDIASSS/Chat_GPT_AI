"""Exact selection and missing-weight failures; synthetic outcomes are not skill evidence."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys,copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import trial_watch as w
import research


def fixture(tmp_path):
 root=tmp_path/'gigaforge';run=root/'runs/research02';run.mkdir(parents=True)
 def write(p,data):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data))
 m=SimpleNamespace(ROOT=root,read=lambda p:json.loads(Path(p).read_text()),write=write,
  sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest(),seal_generation=lambda *a:None,verify_generation=lambda *a:None)
 source=run/'branches/chronos/evolved_40/base/checkpoints/1048576';source.mkdir(parents=True)
 for n in w.FILES:(source/n).write_bytes(('synthetic file '+n).encode())
 files=w.identity(m,source)
 record=dict(trial=62,family='chronos',candidate=str(source.relative_to(run)).replace('/','\\'))
 m.write(run/'lab_state.json',dict(results=[record],last_candidates={'chronos':'branches/other/checkpoints/262144'}))
 rows=[dict(opponent='original_galactus',seed=710620000,side=s,goals_for=1,goals_against=0,outcome=1,seconds=60) for s in (0,1)]
 m.write(run/'evaluations/lab_00062_chronos_confirmation.json',dict(trials=rows,split='confirmation',statistics=dict(delta=.046875)))
 m.write(run/'evaluations/jobs/test.json',dict(identity=dict(models=[dict(family='chronos',hitbox='breakout',files=files)]),result=dict(trials=rows)))
 return m,run,source,files


def test_trial_identity_uses_confirmation_and_both_hashes(tmp_path):
 m,run,source,files=fixture(tmp_path);target=w.trial_identity(m,run,'chronos',62)
 assert target['files']==files and target['split']=='confirmation'
 assert w.find_exact(m,run,target)['path']==str(source)


def test_missing_exact_model_never_opens_latest_or_equal_percentage(tmp_path):
 m,run,source,_=fixture(tmp_path)
 (source/'POLICY.lt').write_bytes(b'different model')
 previous=(run/'lab_state.json').read_bytes()
 with pytest.raises(FileNotFoundError,match='No other bot was opened'):w.prepare(m,run,'chronos',62)
 assert (run/'lab_state.json').read_bytes()==previous
 report=m.read(run/'watch_requests/trial_00062_chronos.json')
 assert report['lookup']['kind']=='missing' and not (run/'watch_pins').exists()


def test_policy_version_is_accepted_only_when_both_files_match(tmp_path):
 import shutil
 m,run,source,_=fixture(tmp_path);target=w.trial_identity(m,run,'chronos',62)
 version=source.parent/'policy_versions/1048576';version.mkdir(parents=True)
 for n in w.FILES:shutil.copy2(source/n,version/n)
 shutil.rmtree(source)
 assert w.find_exact(m,run,target)['path']==str(version)
 (version/'SHARED_HEAD.lt').write_bytes(b'different shared trunk')
 assert w.find_exact(m,run,target)['kind']=='missing'


def test_incomplete_or_ambiguous_evidence_is_rejected(tmp_path):
 m,run,source,_=fixture(tmp_path);job=run/'evaluations/jobs/test.json';data=m.read(job)
 partial=copy.deepcopy(data);partial['result']['trials']=partial['result']['trials'][:1];m.write(job,partial)
 with pytest.raises(ValueError,match='missing or ambiguous'):w.trial_identity(m,run,'chronos',62)
 m.write(job,data);other=copy.deepcopy(data);other['identity']['models'][0]['files']['POLICY.lt']='0'*64;m.write(job.with_name('conflict.json'),other)
 with pytest.raises(ValueError,match='missing or ambiguous'):w.trial_identity(m,run,'chronos',62)


def test_trial_path_cannot_escape_run(tmp_path):
 with pytest.raises(ValueError):w.local_path(tmp_path,'../../another/model')


def test_future_confirmation_actors_survive_rotation_and_are_bounded(tmp_path):
 import shutil
 m,run,source,_=fixture(tmp_path);state=dict(trial=62)
 for i,delta in enumerate((.01,.046875,.02,.001)):
  source.mkdir(parents=True,exist_ok=True)
  for n in w.FILES:(source/n).write_bytes((n+str(i)).encode())
  research.preserve_tested(m,run,state,'chronos',source,dict(split='confirmation',statistics=dict(delta=delta),summary={},baseline_summary={}))
  shutil.rmtree(source)
 entries=state['tested_candidates']['chronos']
 assert [e['statistics']['delta'] for e in entries]==[.046875,.02]
 assert all((run/e['path']/'POLICY.lt').is_file() and not e['verified_champion'] for e in entries)
