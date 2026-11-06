"""Small actual native training/resume and independent export integration."""
import importlib.util,json,os,sys,tempfile
from pathlib import Path
import torch
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_runner',root/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
torch.set_num_threads(1)
run=m.create('native_check','cpu');cfg=m.read(run/'config.json')
from nova.giga_teachers import GigaNetwork
with tempfile.TemporaryDirectory(prefix='native_integration_') as temp:
 temp=Path(temp)
 for family in ('chronos','galactus'):
  recipe=m.base_recipe(run,family,cfg,mode='cross')
  recipe.update(checkpoints=str(temp/family),games=4,simulation_threads=2,rollout=512,batch=256,minibatch=256,trajectory_seconds=.2,max_iterations=1,metrics_file=str(temp/(family+'.jsonl')),stop_at=0)
  initial=GigaNetwork(m.retained(run,family),family).state_dict()
  m.launch(recipe,log=temp/(family+'.log'))
  paths=[p for p in (temp/family).iterdir() if p.name.isdigit()];first=max(paths,key=lambda p:int(p.name))
  warm=GigaNetwork(first,family).state_dict()
  assert all(torch.equal(initial[k],warm[k]) for k in initial),'Warmup modified actor'
  recipe['max_iterations']=3;m.launch(recipe,log=temp/(family+'_resume.log'))
  paths=[p for p in (temp/family).iterdir() if p.name.isdigit()];last=max(paths,key=lambda p:int(p.name))
  trained=GigaNetwork(last,family).state_dict()
  assert any(not torch.equal(initial[k],trained[k]) for k in initial),'Actor did not learn'
  m.seal_generation(last,family);m.verify_generation(last)
  assert (last/'POLICY_OPTIM.lt').stat().st_size>0
  rows=[json.loads(r) for r in Path(recipe['metrics_file']).read_text().splitlines()]
  assert rows[-1]['Total Iterations']==3
  assert rows[0]['Actor Optimizer Steps']==0 and sum(r['Actor Optimizer Steps'] for r in rows)>0
  assert all(r['Critic Optimizer Steps']>0 for r in rows)
  probe=m.base_recipe(run,family,cfg,mode='self')
  probe['evaluation']=dict(candidate=m.descriptor(last,family),baseline=m.descriptor(m.retained(run,family),family),opponents=[m.descriptor(m.retained(run,'galactus'),'galactus')],pairs=1,seconds=.2,seed=271,output=str(temp/(family+'_wdl.json')))
  m.launch(probe,log=temp/(family+'_wdl.log'));result=m.read(probe['evaluation']['output'])
  assert len(result['trials'])==len(result['baseline_trials'])==2
  assert {r['side'] for r in result['trials']}=={0,1}
  print('NATIVE_TRAIN_WARMUP_RESUME_CROSS_WDL_PASS',family,flush=True)
print('NATIVE_INTEGRATION_PASS')
