"""Actual native v2 train/evaluate/resume/actor retention smoke. Not strength evidence."""
from pathlib import Path
import copy,importlib.util,json,sys,tempfile,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('autonomous_runner',ROOT/'run.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
import research
import research_eval


def main():
 torch.set_num_threads(1)
 with tempfile.TemporaryDirectory(prefix='autonomous_native_') as temp:
  temp=Path(temp);original_folder=m.folder;m.folder=lambda name:temp/name
  pointer=ROOT/'active_research.json';old_pointer=pointer.read_bytes() if pointer.exists() else None
  try:
   tiny=dict(block=1024,rollout=512,development_pairs=4,confirmation_pairs=4,
    evaluation_batch_pairs=2,seconds=1,arms=[copy.deepcopy(research.ARMS[1])])
   research.train(m,'lab_v2_ci',choice='cpu',wandb='off',once=True,config=tiny)
   run=m.folder('lab_v2_ci');state=m.read(run/'lab_state.json');cfg=m.read(run/'lab.json')
   assert state['trial']==1 and state['total_decisions']==1024
   current=run/state['last_candidates']['chronos'];initial_hash=m.sha(current/'POLICY.lt')
   panel=[dict(m.descriptor(run/'parents'/f,f),name=f) for f in ('chronos','galactus')]
   data=research_eval.native_jobs(m,run,state,'chronos',current,m.retained(run,'chronos'),panel,'development',cfg)
   again=research_eval.native_jobs(m,run,state,'chronos',current,m.retained(run,'chronos'),panel,'development',cfg)
   assert len(data['trials'])==16 and again['reused_batches']==2 and data['trials']==again['trials']
   # Save a real actor; forced screening metadata below tests storage only.
   research.preserve_promising(m,run,state,'chronos',current,dict(statistics=dict(delta=.1,lower=-.1)))
   saved=run/state['shortlist']['chronos'][0]['path'];m.verify_generation(saved)
   assert m.sha(saved/'POLICY.lt')==initial_hash
   research.train(m,'lab_v2_ci',choice='cpu',wandb='off',once=True)
   state=m.read(run/'lab_state.json');assert state['trial']==2 and state['total_decisions']==2048
   assert m.sha(current/'POLICY.lt')==initial_hash
   assert all(m.retained(run,f)==(run/'parents'/f).resolve() for f in ('chronos','galactus'))
   print('TEST_ONLY_SYNTHETIC_VERDICTS_FOR_V2_CONFIRMATION_FLOW_NOT_STRENGTH_EVIDENCE',flush=True)
   original_evaluate=research.evaluate
   promising=dict(decision='promising',statistics=dict(delta=.25,lower=-.1,upper=.6,by_opponent={'c':.25,'g':.25}),trials=[])
   good=dict(decision='improved',statistics=dict(delta=.25,lower=.1,upper=.4,by_opponent={'c':.25,'g':.25}),trials=[])
   try:
    answers=iter([copy.deepcopy(promising),dict(copy.deepcopy(good),decision='uncertain')])
    research.evaluate=lambda *a,**k:next(answers)
    research.train(m,'lab_v2_ci',choice='cpu',wandb='off',once=True)
    state=m.read(run/'lab_state.json');assert state['confirmations']==1 and state['trial']==3
    assert m.retained(run,'chronos')==(run/'parents/chronos').resolve()
    answers=iter([copy.deepcopy(promising),copy.deepcopy(good)])
    research.train(m,'lab_v2_ci',choice='cpu',wandb='off',once=True)
    state=m.read(run/'lab_state.json');assert state['confirmations']==2 and state['trial']==4
    champion=m.retained(run,'galactus');assert champion!=(run/'parents/galactus').resolve()
    m.verify_generation(champion)
   finally:research.evaluate=original_evaluate
   print('AUTONOMOUS_NATIVE_V2_TRAIN_EVALUATE_CACHE_RESUME_RETAIN_PASS',flush=True)
  finally:
   m.folder=original_folder
   if old_pointer is None:pointer.unlink(missing_ok=True)
   else:pointer.write_bytes(old_pointer)


if __name__=='__main__':main()
