"""Actual fixed-rollout, reward-profile and serial orchestration checks. No strength claim."""
from pathlib import Path
import importlib.util,tempfile,sys,subprocess,json,torch,copy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('native_runner',ROOT/'run.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
import research
from nova.giga_teachers import GigaNetwork

def main():
 torch.set_num_threads(1)
 subprocess.run([str(m.binary()),'--research-selftest'],env=m.environment(),check=True)
 run=m.create('native_check','cpu');cfg=m.read(run/'config.json')
 with tempfile.TemporaryDirectory(prefix='reward_lab_checks_') as temp:
  temp=Path(temp)
  for family in ('chronos','galactus'):
   initial=GigaNetwork(m.retained(run,family),family).state_dict()
   for index,arm in enumerate(research.ARMS):
    folder=temp/family/arm['name'];recipe=m.base_recipe(run,family,cfg,mode='cross')
    recipe.update(checkpoints=str(folder/'checkpoints'),games=4,simulation_threads=2,rollout=512,batch=256,minibatch=256,
     fixed_rollout=True,potential_weights=arm['potential'],freeze_shared=arm['freeze_shared'],anchor_coef=arm['anchor'],actor_lr=arm['lr'],
     trajectory_seconds=60,max_iterations=2,metrics_file=str(folder/'metrics.jsonl'),stop_at=0)
    m.launch(recipe,log=temp/f'{family}_{index}.log')
    rows=[json.loads(x) for x in Path(recipe['metrics_file']).read_text().splitlines()]
    assert len(rows)==2 and all(row['Used Timesteps']==row['Collected Timesteps']==512 for row in rows)
    assert all(row['Data Use Fraction']==1 for row in rows)
    assert rows[0]['Actor Optimizer Steps']==0 and rows[1]['Actor Optimizer Steps']>0
    last=research.latest_in(folder);trained=GigaNetwork(last,family).state_dict()
    if arm['freeze_shared']:assert all(torch.equal(v,trained[k]) for k,v in initial.items() if k.startswith('head.'))
    assert any(not torch.equal(v,trained[k]) for k,v in initial.items() if k.startswith('policy.'))
    print('FIXED_ROLLOUT_REWARD_ACTOR_CHECK_PASS',family,arm['name'],flush=True)
  # Exercise two actual native branch updates, evaluation, state and resume.
  pointer=m.ROOT/'active_research.json';old_pointer=pointer.read_bytes() if pointer.exists() else None
  original_folder=m.folder;m.folder=lambda name:temp/'serial'/name
  try:
   tiny=dict(version='reward-lab-v1',block=1024,rollout=512,development_pairs=1,confirmation_pairs=1,seconds=.2,arms=[copy.deepcopy(research.ARMS[1])])
   research.train(m,'lab_ci',choice='cpu',wandb='off',once=True,config=tiny)
   study=m.folder('lab_ci');state=m.read(study/'lab_state.json');assert state['trial']==1
   first_candidate=study/state['last_candidates']['chronos'];saved=m.sha(first_candidate/'POLICY.lt')
   research.train(m,'lab_ci',choice='cpu',wandb='off',once=True)
   state=m.read(study/'lab_state.json');assert state['trial']==2 and state['total_decisions']==2048
   assert m.sha(first_candidate/'POLICY.lt')==saved
   assert all(m.retained(study,f)==(study/'parents'/f).resolve() for f in ('chronos','galactus'))
   # Regressing one real native branch must not halt the whole coordinator.
   print('TEST_ONLY_INJECTED_WDL_FOR_CONTROLLER_CHECKS_NOT_STRENGTH_EVIDENCE',flush=True)
   original_evaluate=research.evaluate
   fake_bad=dict(decision='regressed',statistics=dict(delta=-.25,lower=-.4,upper=-.1,by_opponent={'c':-.25,'g':-.25}),trials=[])
   research.evaluate=lambda *a,**k:copy.deepcopy(fake_bad)
   research.train(m,'lab_ci',choice='cpu',wandb='off',once=True)
   state=m.read(study/'lab_state.json');assert state['trial']==3 and state['branches']['chronos/attack']['restart']==1
   assert m.retained(study,'chronos')==(study/'parents/chronos').resolve()
   # Only a positive screen followed by positive confirmation may promote.
   fake_good=dict(decision='improved',statistics=dict(delta=.25,lower=.1,upper=.4,by_opponent={'c':.25,'g':.25}),trials=[])
   answers=iter([copy.deepcopy(fake_good),dict(copy.deepcopy(fake_good),decision='uncertain')])
   research.evaluate=lambda *a,**k:next(answers)
   research.train(m,'lab_ci',choice='cpu',wandb='off',once=True)
   assert m.retained(study,'galactus')==(study/'parents/galactus').resolve()
   answers=iter([copy.deepcopy(fake_good),copy.deepcopy(fake_good)])
   research.evaluate=lambda *a,**k:next(answers)
   research.train(m,'lab_ci',choice='cpu',wandb='off',once=True)
   best=m.retained(study,'chronos');assert best!=(study/'parents/chronos').resolve()
   exported=m.candidate_actor(study,'chronos');actor=torch.jit.load(str(exported));native=GigaNetwork(best,'chronos')
   x=torch.linspace(-1,1,2*228).reshape(2,228)
   with torch.inference_mode():torch.testing.assert_close(actor(x),native(x[:,:225]),rtol=0,atol=0)
   # Protected copies must survive rotating/removing a rejected/training directory.
   candidate=study/m.read(study/'lab_state.json')['last_candidates']['chronos']
   import shutil;shutil.rmtree(candidate.parent)
   m.verify_generation(best)
   research.evaluate=original_evaluate

  finally:
   m.folder=original_folder
   if old_pointer is None:pointer.unlink(missing_ok=True)
   else:pointer.write_bytes(old_pointer)
 print('RESEARCH_NATIVE_FIXED_DATAUSE_REWARD_SEARCH_RESUME_PASS')

if __name__=='__main__':main()
