import json
from collections import deque
import numpy as np
import pytest
import torch
from duelforge.runtime import config,batch,load,save,sha
from duelforge.acquisition import stage_config
from duelforge.held_ball import HeldBallBatch,target_states
from duelforge.held_experiment import setup,probe,verify_stationary_contract,NEUTRAL
from duelforge.observation import ACTIONS

JUMP=int(np.flatnonzero((ACTIONS[:,5]==1)&(ACTIONS[:,2]==0)&(ACTIONS[:,4]==0)&(ACTIONS[:,6]==0))[0])

def cfg():
 c=stage_config(config(),'trajectory');c.update(n_envs=4,width=32,device='cpu',torch_threads=1)
 c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
 c['held_ball']={'version':'stationary-air-v1','seconds':4.,'drill_entropy':.02,'contact_bonus':1.,'approach_weight':.02}
 return c

def scene():
 w=target_states(np.random.default_rng(6),1)[0];w[0,:3]=[0,0,310];w[0,3:9]=0
 w[1,:3]=[0,-150,17];w[1,9:12]=[0,1,0];w[1,3:6]=[0,300,0]
 w[2,:3]=[3000,3000,17];w[2,3:9]=0
 return w

def test_stationary_contract_and_live_jump_state_no_per_frame_injection():
 c=cfg();assert verify_stationary_contract(c)['passed']
 e=HeldBallBatch(batch(c,n=1),c,17,force=1);w=scene();w[1,:3]=[2000,0,17];w[1,3:9]=0
 e.env.inject(0,w);e.raw=e.env.observe()
 original=e.env
 class ResetGuard:
  def __getattr__(self,name):
   if name in ('inject','reset_one'):raise AssertionError('No episode ended; no state reset allowed')
   return getattr(original,name)
 e.env=ResetGuard();heights=[]
 for _ in range(7):
  r=e.step(np.array([[JUMP,NEUTRAL]],np.int64));heights.append(float(r['final_world'][0,1,2]))
  np.testing.assert_array_equal(r['final_world'][0,0,:9],w[0,:9])
 assert max(heights)>90 and r['final_world'][0,1,17]>.5

def test_real_high_contact_is_rewarded_and_resets_keep_final_state():
 c=cfg();e=HeldBallBatch(batch(c,n=1),c,17,force=1);w=scene()
 e.env.inject(0,w);e.raw=e.env.observe();e.seen[:]=False;e.elapsed[:]=0
 np.testing.assert_array_equal(e.raw['mask'],e.env.observe()['mask']);assert e.raw['mask'][0,0,JUMP]
 for _ in range(21):
  r=e.step(np.array([[JUMP,NEUTRAL]],np.int64))
  if r['reward_parts'][0,0,2]>0:
   assert r['reward_parts'][0,0,2]==1 and r['terminated'][0] and not r['truncated'][0]
   assert r['final_world'][0,1,2]>65 and r['world'][0,1,2]<30
   assert e.last['successful_held']==1;break
 else:raise AssertionError('The physical jump must reach the suspended target')

def test_drill_timeout_terminal_and_no_airtime_or_jump_bonus():
 c=cfg();c['held_ball']['approach_weight']=0;e=HeldBallBatch(batch(c,n=1),c,17,force=1)
 w=scene();w[1:,:3]=[[3000,0,17],[-3000,0,17]];w[1:,3:9]=0
 e.env.inject(0,w);e.raw=e.env.observe();e.elapsed[:]=0
 for k in range(61):
  r=e.step(np.full((1,2),JUMP,np.int64))
  np.testing.assert_array_equal(r['reward_parts'][0,:,2],0)
  assert not r['rewards'].any()
  if r['terminated'][0]:
   assert 59<=k<=60 and not r['truncated'][0] and e.last['successful_held']==0;break
 else:raise AssertionError('Four-second finite drill must terminate')

def test_entropy_is_per_task_and_curriculum_restores():
 c=cfg();e=HeldBallBatch(batch(c,n=3),c,11)
 e.tasks[:]=[0,1,2];np.testing.assert_allclose(e.entropy_coefficients(),[[.003,.003],[.02,.02],[.02,.02]])
 state={'level':2,'transfer':True,'successes':[True,False,True]};e.restore_curriculum(state)
 assert e.curriculum_state()==state
 e.restore_curriculum({'level':0,'transfer':False,'successes':[True]*128})
 e.step(np.full((3,2),NEUTRAL,np.int64));assert e.level==0 and len(e.successes)==128

def test_short_drills_do_not_get_diluted_by_long_matches():
 c=cfg();e=HeldBallBatch(batch(c,n=32),c,712)
 assignment=e.tasks.copy();assert (assignment==0).sum()==16
 assert (assignment==1).sum()==11 and (assignment==2).sum()==5
 for _ in range(125):e.step(np.full((32,2),NEUTRAL,np.int64))
 np.testing.assert_array_equal(e.tasks,assignment)

def test_frozen_opponent_contact_does_not_advance_curriculum():
 c=cfg();e=HeldBallBatch(batch(c,n=1),c,17,force=1);w=scene()
 e.env.inject(0,w);e.raw=e.env.observe();e.seen[:]=False;e.learning_rows[:]=[[False,True]]
 for _ in range(21):
  r=e.step(np.array([[JUMP,NEUTRAL]],np.int64))
  if r['terminated'][0]:
   assert r['reward_parts'][0,0,2]==1 and e.last['successful_held']==0
   assert list(e.successes)==[False];break
 else:raise AssertionError('Physical frozen-opponent hit expected')

def test_normal_rows_keep_actual_goal_and_concede_rewards():
 c=cfg()
 for direction in (-1,1):
  e=HeldBallBatch(batch(c,n=1),c,17);w=scene()
  w[0,:3]=[0,direction*4800,200];w[0,3:6]=[0,direction*1600,0]
  w[1:,:3]=[[-3000,0,17],[3000,0,17]];w[1:,3:9]=0
  e.env.inject(0,w);e.raw=e.env.observe();e.tasks[:]=0;e.drill[:]=False
  for _ in range(15):
   r=e.step(np.full((1,2),NEUTRAL,np.int64))
   if r['terminated'][0]:
    np.testing.assert_array_equal(r['reward_parts'][0,:,0],[direction,-direction])
    assert r['rewards'][0,0]*direction>0 and r['rewards'][0,1]*direction<0;break
  else:raise AssertionError('Physical goal must register')

def test_fork_real_ppo_resume_probes_and_bare_eval_preserve_source(tmp_path):
 from duelforge.train import train
 from duelforge.evaluate import evaluate
 parent=tmp_path/'parent';train(parent,cfg(),minutes=1,max_updates=1)
 before=load(parent/'latest.pt');identity=sha(parent/'latest.pt');root=tmp_path/'held01';folder=setup(root,parent/'latest.pt')
 child=load(folder/'latest.pt')
 for k in before['model']:
  if k.startswith('actor.'):torch.testing.assert_close(child['model'][k],before['model'][k],atol=0,rtol=0)
 assert child['history']==['source_reference.pt']
 count=train(folder,minutes=1,max_updates=2);child=load(folder/'latest.pt');assert count>before['learning_transitions']
 assert child['held_curriculum']['level']==0
 # A real saved curriculum survives PPO resume instead of resetting to easiest.
 child['held_curriculum']={'level':1,'transfer':False,'successes':[True]};save(folder/'latest.pt',child)
 train(folder,minutes=1,max_updates=1);assert load(folder/'latest.pt')['held_curriculum']['level']==1
 identity_child=sha(folder/'latest.pt');r=probe(folder/'latest.pt',pairs=2);assert r['trials']==4
 evaluate(folder,games_per_context=4,seconds=1,seed=99113,contexts=['match'])
 assert sha(folder/'latest.pt')==identity_child and sha(parent/'latest.pt')==identity
 # Runtime factory remains native; only explicit training/watch wraps it.
 assert not isinstance(batch(child['config'],n=1),HeldBallBatch)
 metrics=[json.loads(x) for x in (folder/'metrics.jsonl').read_text().splitlines()]
 assert all(.003-1e-6<=x['train/entropy_coefficient']<=.02+1e-6 for x in metrics)
 assert 'held/completed_held' in metrics[-1]

def test_watch_uses_neural_actor_and_exact_optional_scaffold(tmp_path):
 from duelforge.train import train
 from duelforge.watch import watch
 train(tmp_path,cfg(),minutes=1,max_updates=1)
 out=watch(tmp_path,seconds=1,headless=True,frames=3,opponent='self',held_drills=True)
 assert json.loads((out/'metadata.json').read_text())['stationary_air_scaffold']
 frames=np.load(out/'frames.npz')
 assert frames['world'].shape[0]==3 and frames['actions'].shape==(3,2)
 np.testing.assert_array_equal(frames['world'][:,0,:3],np.repeat(frames['world'][0:1,0,:3],3,axis=0))
 out=watch(tmp_path,seconds=1,headless=True,frames=2,opponent='self')
 assert not json.loads((out/'metadata.json').read_text())['stationary_air_scaffold']

def test_invalid_drill_settings_fail_before_training():
 c=cfg();c['held_ball']['drill_entropy']=.5
 with pytest.raises(ValueError):HeldBallBatch(batch(c,n=1),c,17)

def test_bounded_controller_produces_skill_match_and_report_artifacts(tmp_path):
 from duelforge.train import train
 from duelforge.held_experiment import start
 parent=tmp_path/'source';train(parent,cfg(),minutes=1,max_updates=1)
 identity=sha(parent/'latest.pt');root=tmp_path/'new_held'
 start(root,parent/'latest.pt',steps=32,pairs=2,games=4)
 state=json.loads((root/'curriculum.json').read_text());assert state['status']=='paused'
 result=json.loads(next(root.glob('held_result_*.json')).read_text())
 assert result['matches']['games']==4 and result['after']['current_level_held']['trials']==4
 assert (root/'stationary_physics_check.json').is_file() and sha(parent/'latest.pt')==identity


def test_greedy_skill_gate_not_exploratory_touches_controls_progression():
 from duelforge.held_experiment import next_curriculum
 current={'level':0,'transfer':False,'successes':[True]*128}
 result={'clear_match_regression':False,'after':{'held':{'contact_rate':.9},'current_level_held':{'contact_rate':.9},'current_level_moving':{'contact_rate':.6}},'source_same_cases':{'held':{'contact_rate':.9}}}
 assert next_curriculum(current,result)['level']==1
 assert current['level']==0
 result['after']['current_level_held']['contact_rate']=.4
 assert next_curriculum(current,result)==current
 result['after']['current_level_held']['contact_rate']=.9;result['clear_match_regression']=True
 assert next_curriculum(current,result)==current
