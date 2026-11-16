import copy,json,os,shutil,tempfile,time,zipfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,load,save,sha,model,device,batch,lock,atomic_json
from .acquisition_experiment import fork_stage
from .held_ball import target_states
from .air_recovery import elevated_hits
from .observation import ACTIONS

NEUTRAL=int(np.flatnonzero(np.all(ACTIONS==0,axis=1))[0])

def next_curriculum(current,result):
 """Advance at most one level per completed, frozen-policy-tested block."""
 out=copy.deepcopy(current)
 if result['clear_match_regression'] or len(current['successes'])<128:return out
 a=result['after'];b=result['source_same_cases']
 if (a['held']['contact_rate']<b['held']['contact_rate']-.1
     or a['current_level_held']['contact_rate']<.75
     or a['current_level_moving']['contact_rate']<.5):return out
 if current['level']<2:out['level']+=1
 else:out['transfer']=True
 out['successes']=[];return out

def verify_stationary_contract(cfg):
 """Check the installed engine before relying on its zero-motion sleep."""
 c=copy.deepcopy(cfg);c['predictive']={'enabled':False}
 e=batch(c,n=1,seed=111,seconds=20);w=target_states(np.random.default_rng(11),1)[0]
 w[0,:3]=[0,0,500];w[1,:3]=[3000,3000,17];w[2,:3]=[-3000,-3000,17];w[1:,3:9]=0
 e.inject(0,w);a=np.full((1,2),NEUTRAL,np.int64)
 for _ in range(45):r=e.step(a)
 stationary=bool(np.array_equal(r['final_world'][0,0,:9],w[0,:9]))
 w[0,5]=1;e.inject(0,w);r=e.step(a)
 released=bool(r['final_world'][0,0,2]<500 and r['final_world'][0,0,5]<0)
 if not stationary or not released:raise RuntimeError('Installed engine stationary/release contract failed; no training started')
 return {'stationary_exact_for_seconds':3,'nonzero_velocity_releases_gravity':released,'passed':True}

def setup(root,source):
 root=Path(root);source=Path(source)
 if root.exists():
  state=json.loads((root/'curriculum.json').read_text())
  if state['version']!='stationary-air-v1' or sha(root/'baseline.pt')!=state['source_sha256']:raise ValueError('Stationary experiment identity changed')
  return root/'03_trajectory'
 root.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.held_fork_',dir=root.parent))
 try:
  shutil.copy2(source,stage/'baseline.pt');ck=load(source);folder=stage/'03_trajectory'
  fork_stage(stage/'baseline.pt',folder,stage/'baseline.pt','trajectory',ck['learning_transitions'])
  child=load(folder/'latest.pt');c=child['config'];c.pop('air_recovery',None)
  if 'jump_bootstrap' in c:c['parent_jump_bootstrap']=c.pop('jump_bootstrap')
  c['objective']='stationary_then_released_air_contacts_v1';c['acquisition'].update(drill_fraction=0,contact_ground_only=False)
  c['held_ball']={'version':'stationary-air-v1','seconds':4.,'drill_entropy':.02,'contact_bonus':1.,'approach_weight':.02,
    'distribution':'35% stationary, 15% released, 50% normal; 15/35/50 after success at level 2',
    'advancement':'At block boundaries: 128 completed stationary trials, greedy held >=75%, moving >=50%, easy-contact and match retention',
    'levels':[[240,340,180,420],[300,450,250,650],[400,650,350,900]]}
  c['wandb']['name']='held01_stationary_then_moving';child['config']=c
  (folder/'history').mkdir(exist_ok=True)
  save(folder/'history/source_reference.pt',{'model':ck['model'],'config':ck['config'],'learning_transitions':ck['learning_transitions']})
  child['history']=['source_reference.pt'];save(folder/'latest.pt',child);atomic_json(folder/'config.json',c)
  provenance=json.loads((folder/'provenance.json').read_text())
  provenance.update(objective=c['objective'],history='Frozen source reference seeded; subsequent snapshots follow existing league rotation')
  atomic_json(folder/'provenance.json',provenance)
  atomic_json(stage/'curriculum.json',{'version':'stationary-air-v1','stage_index':2,'status':'ready',
    'source_sha256':sha(stage/'baseline.pt'),'origin_transitions':ck['learning_transitions'],
    'scope':'Training-only stationary-ball scaffold mixed with normal physics. Source preserved; no promotion.'})
  os.rename(stage,root)
 finally:
  if stage.exists():shutil.rmtree(stage)
 return root/'03_trajectory'

def source_checkpoint():
 folder=ROOT/'runs/jump01/03_trajectory';resultfile=ROOT/'runs/jump01/bootstrap_result.json'
 if not (folder/'latest.pt').is_file() or not resultfile.is_file():
  raise FileNotFoundError('Tested jump01 candidate required. Finish 50_BOOTSTRAP_JUMP_SKILL.bat first; no older/failed actor was substituted.')
 result=json.loads(resultfile.read_text())
 if sha(folder/'latest.pt')!=result['candidate_sha256']:raise ValueError('Bootstrap candidate changed since its tests; no substitute source chosen')
 if result['heldout_candidate']['contact_rate']<.5 or result['matches']['score_interval_95'][1]<.5:
  raise ValueError('Bootstrap candidate did not pass skill/match retention checks')
 return folder/'latest.pt'

def probe(checkpoint,level=0,released=False,seed=0xB0100000,pairs=32):
 actor,ck,_=model(Path(checkpoint).parent,checkpoint=checkpoint);c=copy.deepcopy(ck['config']);c['predictive']={'enabled':False}
 dev=device(c);torch.set_num_threads(c['torch_threads']);actor.to(dev)
 n=2*pairs;w=target_states(np.random.default_rng(seed),pairs,level,released)
 w[:,2,:3]=[3400,4200,17];w[:,2,3:9]=0
 worlds=np.empty((n,3,32),np.float32);worlds[0::2]=w
 rotated=w.copy();rotated[:,:,:15]*=np.array([-1,-1,1]*5);rotated[:,[1,2]]=rotated[:,[2,1]];worlds[1::2]=rotated
 e=batch(c,n=n,seed=seed,seconds=5)
 for i,state in enumerate(worlds):e.inject(i,state)
 raw=e.observe();ix=np.arange(n);colors=ix%2;ticks=np.zeros(n,np.int64);done=np.zeros(n,bool);success=done.copy();jump=done.copy()
 with torch.inference_mode():
  while not done.all():
   ac=np.full((n,2),NEUTRAL,np.int64)
   ac[ix,colors]=actor(torch.as_tensor(raw['obs'][ix,colors],device=dev),torch.as_tensor(raw['mask'][ix,colors],device=dev))[0].argmax(-1).cpu().numpy()
   active=~done;jump|=active&(ACTIONS[ac[ix,colors],5]>.5)
   before=raw['world'];raw=e.step(ac,np.where(done,0,np.maximum(0,480-ticks)));ticks+=raw['info'][:,3].astype(np.int64)
   hit=active&elevated_hits(before,raw)[ix,colors];success|=hit;done|=hit|(ticks>=480)|raw['terminated']
 return {'checkpoint_sha256':sha(checkpoint),'level':level,'stationary':not released,'seed':seed,'pairs':pairs,'trials':n,
   'contact_rate':float(success.mean()),'jump_rate':float(jump.mean()),'raw_contacts':success.tolist(),'raw_jump':jump.tolist(),
   'scope':'Stationary or released scaffold check, full native controls; not a regulation match.'}

def report(root):
 from .report import report as stage_report
 root=Path(root);stage=stage_report(root/'03_trajectory');out=ROOT/f'DuelForge_held01_report_{time.time_ns()}.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for p in root.glob('*.json'):z.write(p,p.name)
  z.write(stage,'stage_reports/'+stage.name);z.write(ROOT/'STATIONARY_AIR.md','STATIONARY_AIR.md')
  z.write(ROOT/'tools/held_air.py','source/tools/held_air.py')
 print('HELD_REPORT_READY:',out,flush=True);return out

def start(root=None,source=None,steps=500_000,pairs=32,games=200):
 from .train import train
 from .evaluate import evaluate
 root=Path(root or ROOT/'runs/held01')
 if not 0<steps<=2_000_000:raise ValueError('Use a bounded 1..2M-step trial')
 if not root.exists():folder=setup(root,source or source_checkpoint())
 else:folder=setup(root,root/'baseline.pt')
 with lock(root):
  root.joinpath('STOP').unlink(missing_ok=True)
  previous=sorted(root.glob('held_result_*.json'))
  if previous:
   prior=json.loads(previous[-1].read_text())
   if prior['candidate_sha256']==sha(folder/'latest.pt') and prior['clear_match_regression']:
    print('HELD_REGRESSION_PAUSED: source preserved; review result before another trial.',flush=True)
    report(root);return
  ck=load(folder/'latest.pt');count=ck['learning_transitions']
  if previous and prior['candidate_sha256']==sha(folder/'latest.pt'):
   current=ck['held_curriculum'];proposed=next_curriculum(current,prior)
   if proposed!=current:
    ck['held_curriculum']=proposed;save(folder/'latest.pt',ck)
    atomic_json(root/f'curriculum_advance_{count}.json',{'tested_checkpoint_sha256':prior['candidate_sha256'],
      'from':current,'to':proposed,'actor_weights_changed':False,'reason':'Greedy contact/moving/retention gates passed'})
  atomic_json(root/'stationary_physics_check.json',verify_stationary_contract(ck['config']))
  state=json.loads((root/'curriculum.json').read_text());state.update(status='training',active_folder='03_trajectory')
  atomic_json(root/'curriculum.json',state)
  print('STATIONARY_AIR: +',steps,'learner transitions; 35% stationary / 15% released / 50% normal. Drill entropy .020; normal .003. Then probes and normal matches.',flush=True)
  before={'held':probe(folder/'latest.pt',seed=0xB0100000,pairs=pairs),
          'moving':probe(folder/'latest.pt',released=True,seed=0xB0200000,pairs=pairs)}
  atomic_json(root/f'held_before_{count}.json',before)
  reached=train(folder,minutes=90,stop_at_transitions=count+steps,external_stop_file=root/'STOP')
  if reached>=count+steps and not (root/'STOP').exists() and not (folder/'STOP').exists():
   current_level=load(folder/'latest.pt')['held_curriculum']['level']
   after={'held':probe(folder/'latest.pt',seed=0xB0300000,pairs=pairs),
          'moving':probe(folder/'latest.pt',released=True,seed=0xB0400000,pairs=pairs),
          'current_level_held':probe(folder/'latest.pt',level=current_level,seed=0xB0500000,pairs=pairs),
          'current_level_moving':probe(folder/'latest.pt',level=current_level,released=True,seed=0xB0600000,pairs=pairs)}
   baseline={'held':probe(root/'baseline.pt',seed=0xB0300000,pairs=pairs),
             'moving':probe(root/'baseline.pt',released=True,seed=0xB0400000,pairs=pairs),
             'current_level_held':probe(root/'baseline.pt',level=current_level,seed=0xB0500000,pairs=pairs),
             'current_level_moving':probe(root/'baseline.pt',level=current_level,released=True,seed=0xB0600000,pairs=pairs)}
   matches=evaluate(folder,games_per_context=games,seconds=100,contexts=['match'])
   atomic_json(root/f'held_result_{reached}.json',{'before':before,'after':after,'source_same_cases':baseline,
       'candidate_sha256':sha(folder/'latest.pt'),'curriculum':load(folder/'latest.pt')['held_curriculum'],
       'matches':matches['overall'],'clear_match_regression':bool(matches['overall']['score_interval_95'][1]<.5),
       'promotion':'none; stationary scaffold success alone does not certify normal aerial skill'})
  state=json.loads((root/'curriculum.json').read_text());state.update(status='paused',learning_transitions=reached,
          additional_steps=reached-state['origin_transitions']);atomic_json(root/'curriculum.json',state);report(root)
