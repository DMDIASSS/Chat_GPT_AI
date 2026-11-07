"""Evidence-triggered continuation policy; original objectives remain immutable."""
from pathlib import Path
import copy,json


def work_times(m,run):
 evaluation=0.
 for p in (run/'evaluations').glob('lab_*.json'):
  row=m.read(p);evaluation+=row.get('invocation_wall_seconds',row.get('wall_seconds',0))
 native=0.
 for p in (run/'branches').glob('*/*/*/metrics.jsonl'):
  for line in p.read_text().splitlines():
   row=json.loads(line);native+=row.get('Collection Time',0)+row.get('Consumption Time',0)
 return dict(evaluation_seconds=evaluation,native_work_seconds=native)


def configure(m,run,state,cfg):
 effective=copy.deepcopy(cfg)
 if cfg['version']!='reward-lab-v2':return effective
 if not state.get('pacing'):
  results=state.get('results',[])
  if len(results)<24 or any(r['decision']=='improved' for r in results):return effective
  times=work_times(m,run)
  if times['native_work_seconds']<=0 or times['evaluation_seconds']<2*times['native_work_seconds']:return effective
  policy=dict(version='training-focus-v1',base_config_sha256=m.sha(run/'lab.json'),
   activated_at_trial=state['trial'],evidence=times,
   reason='At least 24 trials without an accepted gain; evaluation cost exceeds twice native learning work.',
   overrides=dict(block=4*cfg['block'],max_branch_decisions=4*cfg['max_branch_decisions']),
   profile_schedule='Within each family: control, strongest measured non-control, control, exploration. Each trial still gets a fixed-budget screen.',
   objective_and_promotion_changed=False)
  path=run/'controller_configs/training-focus-v1.json';m.write(path,policy)
  state['pacing']=dict(path=str(path.relative_to(run)),sha256=m.sha(path))
 entry=state['pacing'];path=run/entry['path']
 if m.sha(path)!=entry['sha256']:raise ValueError('Research pacing configuration changed')
 policy=m.read(path)
 if policy['base_config_sha256']!=m.sha(run/'lab.json'):raise ValueError('Pacing belongs to a different base experiment')
 effective.update(policy['overrides']);effective['profile_schedule']='training-focus-v1'
 print('RESEARCH_PACING:',policy['version'],'decisions per screen',effective['block'],'branch cap',effective['max_branch_decisions'],'original objectives and promotion tests preserved.',flush=True)
 return effective


def choose(state,family,arms,fallback):
 turn=state['trial']//2%4
 if turn==3:return fallback(state,family,arms)
 control=next((a for a in arms if a['name']=='control'),None)
 if turn in (0,2) and control:return control
 choices=[a for a in arms if a['name']!='control']
 if not choices:return fallback(state,family,arms)
 def score(a):
  value=state.get('arms',{}).get(family+'/'+a['name'],{})
  return value.get('score',0)/max(1,value.get('n',0)) if value.get('n',0)>=2 else -10
 return max(choices,key=score)
