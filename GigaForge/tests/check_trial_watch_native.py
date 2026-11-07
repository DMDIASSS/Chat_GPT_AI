"""Real native actor -> exact hash lookup -> pinned viewer actor; no skill claim."""
from pathlib import Path
import importlib.util,sys,tempfile,json,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('trial_runner',ROOT/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import trial_watch
from nova.giga_teachers import GigaNetwork
from nova.forge_models import check_actor


def main():
 torch.set_num_threads(1)
 from nova.teachers import fetch_teachers,verify_teacher
 fetch_teachers(['chronos']);parent=verify_teacher('chronos')
 with tempfile.TemporaryDirectory(prefix='trial_watch_check_') as temp:
  temp=Path(temp);run=temp/'research02';source=run/'branches/chronos/test/checkpoints/1048576';source.mkdir(parents=True)
  import shutil
  for n in trial_watch.FILES:shutil.copy2(parent/n,source/n)
  files=trial_watch.identity(m,source)
  m.write(run/'lab_state.json',dict(results=[dict(trial=62,family='chronos',candidate=str(source.relative_to(run)))],last_candidates={}))
  rows=[dict(opponent='fixture',seed=710620000,side=s,goals_for=0,goals_against=0,outcome=0,seconds=60) for s in (0,1)]
  m.write(run/'evaluations/lab_00062_chronos_confirmation.json',dict(trials=rows,split='confirmation',statistics=dict(delta=.046875)))
  m.write(run/'evaluations/jobs/test.json',dict(identity=dict(models=[dict(family='chronos',hitbox='breakout',files=files)]),result=dict(trials=rows)))
  print('SYNTHETIC_TRIAL_RECORD_FOR_SELECTION_TEST_ONLY_NOT_THE_USERS_TRAINED_ACTOR',flush=True)
  actor=trial_watch.prepare(m,run,'chronos',62);meta=check_actor(actor,'chronos')
  assert meta['role']=='trial 62 candidate (unverified)' and meta['contract']['hitbox']=='breakout'
  x=torch.linspace(-1,1,4*228).reshape(4,228)
  with torch.inference_mode():torch.testing.assert_close(torch.jit.load(str(actor))(x),GigaNetwork(source,'chronos')(x[:,:225]),rtol=0,atol=0)
  shutil.rmtree(source);assert trial_watch.prepare(m,run,'chronos',62)==actor
  # Recover from a prior direct actor export after all split weights are gone.
  cache=run/'export_actors/chronos/cache.lt';cache.parent.mkdir(parents=True);shutil.copy2(actor,cache);shutil.copy2(str(actor)+'.json',str(cache)+'.json')
  shutil.rmtree(run/'watch_pins');recovered=trial_watch.prepare(m,run,'chronos',62)
  assert m.sha(recovered)==m.sha(cache)
 print('EXACT_TRIAL_NATIVE_ACTOR_PARITY_PIN_AND_EXPORT_RECOVERY_PASS',flush=True)


if __name__=='__main__':main()
