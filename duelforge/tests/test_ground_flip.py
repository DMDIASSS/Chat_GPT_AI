import copy,json
from pathlib import Path
import numpy as np
import pytest,torch
from duelforge.runtime import config,batch,load,sha
from duelforge.acquisition import stage_config
from duelforge.ground_flip import GroundFlipBatch,RECIPE,terminal_penalty,NEUTRAL
from duelforge.flip_experiment import calibration,calibrated_controls,setup,probe,balanced_cases,install_cases,DRIVE,JUMP,DODGE
from duelforge.observation import ACTIONS

def cfg():
 c=stage_config(config(),'trajectory');c.update(device='cpu',width=32,n_envs=4,torch_threads=1)
 c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
 c['flip_drill']=copy.deepcopy(RECIPE);return c

def test_no_boost_flip_reaches_where_drive_and_jump_miss():
 r=calibration(cfg());assert r['passed'] and r['jump_release_dodge']['successes']==64
 assert r['drive']['contacts']==r['single_jump']['contacts']==0
 assert r['jump_release_dodge']['physical_flips']==64
 assert r['jump_release_dodge']['peak_active_car_boost']==0

def test_no_flip_jump_timing_sweep_cannot_hit_before_deadline():
 for start in (0,4,8,12,16,20,24,28,31):
  for hold in (1,2,3):
   r=calibrated_controls(cfg(),'jump',seed=0xE1400000+start*7+hold,pairs=4,jump_at=start,jump_hold=hold)
   assert r['contacts']==0 and r['physical_flips']==0

def test_penalty_is_terminal_and_closer_failures_cost_less():
 p=terminal_penalty(np.array([2250,1125,225,0,150]),np.full(5,2250),[False,False,False,False,True])
 np.testing.assert_allclose(p,[-1,-.5,-.1,-.01,0],atol=1e-7)
 e=GroundFlipBatch(batch(cfg(),n=1),cfg(),17,force=True,color=0)
 total=0.;ticks=0
 for k in range(33):
  r=e.step(np.full((1,2),NEUTRAL,np.int64));ticks+=r['info'][0,3];total+=r['rewards'][0,0]
  if k<32:assert r['rewards'][0,0]==0 and not r['terminated'][0]
 assert ticks==264 and r['terminated'][0] and not r['truncated'][0]
 assert total<-.99 and r['flip_drill']['success'][0]==False

def test_success_is_zero_penalty_and_real_final_state_precedes_reset():
 c=cfg();e=GroundFlipBatch(batch(c,n=1),c,17,force=True,color=0)
 w,col=balanced_cases(0xE1100000,1);install_cases(e,w[:1],col[:1]);success=False
 for t in range(33):
  action=DRIVE if t<14 else JUMP if t==14 else DODGE if t==16 else NEUTRAL
  r=e.step(np.array([[action,NEUTRAL]],np.int64))
  if r['terminated'][0]:
   assert r['flip_drill']['success'][0] and r['flip_drill']['flipped'][0]
   assert r['rewards'][0,0]==0 and r['flip_drill']['penalty'][0]==0
   assert not np.array_equal(r['final_world'],r['world']);success=True;break
 assert success

def test_nonflip_physical_contact_cannot_pass():
 c=cfg();e=GroundFlipBatch(batch(c,n=1),c,17,force=True,color=0)
 w=e.observe()['world'][0].copy();direction=w[1,9:12];w[1,:3]=w[0,:3]-direction*220;w[1,2]=17;w[1,3:6]=direction*1000
 install_cases(e,w[None],np.array([0]))
 for _ in range(10):
  r=e.step(np.array([[DRIVE,NEUTRAL]],np.int64))
  if r['terminated'][0]:
   assert r['info'][0,1] and not r['flip_drill']['success'][0] and r['rewards'][0,0]<0;break
 else:raise AssertionError('Physical ground contact expected')

def test_no_boost_full_jump_masks_parked_rows_and_fixed_arena_roles():
 c=cfg();e=GroundFlipBatch(batch(c,n=16),c,81)
 drill=e.drill.copy();assert drill.sum()==8
 assert not e.observe()['mask'][drill][...,ACTIONS[:,6]>0].any()
 assert e.observe()['mask'][drill,:,JUMP].any()
 assert e.learner_rows().sum()==24
 assert np.count_nonzero(e.observe()['mask'][np.flatnonzero(drill),1-e.colors[drill]],axis=-1).tolist()==[1]*8
 weights=e.entropy_coefficients();np.testing.assert_allclose(weights[drill],.02);np.testing.assert_allclose(weights[~drill],.003)
 for _ in range(70):e.step(np.full((16,2),NEUTRAL,np.int64))
 np.testing.assert_array_equal(e.drill,drill)
 # An accidental fuel pickup cannot enable boost; action is rejected instead
 # of silently changing the PPO action whose log-probability was recorded.
 i=int(np.flatnonzero(drill)[0]);ac=np.full((16,2),NEUTRAL,np.int64)
 ac[i,e.colors[i]]=int(np.flatnonzero(ACTIONS[:,6]>0)[0])
 with pytest.raises(ValueError):e.step(ac)

def test_normal_play_keeps_goals_and_concessions():
 c=cfg();e=GroundFlipBatch(batch(c,n=1),c,17)
 assert not e.drill.any()
 for sign in (-1,1):
  w=e.observe()['world'][0].copy();w[0,:3]=[0,sign*4800,200];w[0,3:6]=[0,sign*1600,0]
  w[1:,:3]=[[-3000,0,17],[3000,0,17]];w[1:,3:9]=0
  e.env.inject(0,w);e.raw=e._mask(e.env.observe())
  for _ in range(15):
   r=e.step(np.full((1,2),NEUTRAL,np.int64))
   if r['terminated'][0]:
    np.testing.assert_array_equal(r['reward_parts'][0,:,0],[sign,-sign]);assert r['rewards'][0,0]*sign>0;break
  else:raise AssertionError('Actual goal expected')

def test_real_ppo_excludes_parked_rows_preserves_source_and_resumes(tmp_path):
 from duelforge.train import train
 parent=tmp_path/'parent';train(parent,cfg(),minutes=1,max_updates=1)
 identity=sha(parent/'latest.pt');before=load(parent/'latest.pt');folder=setup(tmp_path/'flip01',parent/'latest.pt')
 child=load(folder/'latest.pt')
 for key in before['model']:
  if key.startswith('actor.'):torch.testing.assert_close(child['model'][key],before['model'][key],atol=0,rtol=0)
 count=train(folder,minutes=1,max_updates=2)
 assert count-before['learning_transitions']<=2*8*6 # 4 arenas: 2 normal pairs + 2 single learners
 ck=load(folder/'latest.pt');train(folder,minutes=1,max_updates=1)
 assert load(folder/'latest.pt')['updates']==ck['updates']+1
 identity_child=sha(folder/'latest.pt');r=probe(folder/'latest.pt',pairs=2)
 assert r['trials']==4 and sha(folder/'latest.pt')==identity_child and sha(parent/'latest.pt')==identity
 assert not isinstance(batch(child['config'],n=1),GroundFlipBatch)

def test_controller_watch_and_export_pipeline(tmp_path):
 from duelforge.train import train
 from duelforge.flip_experiment import start
 from duelforge.watch import watch
 from duelforge.export import export
 parent=tmp_path/'source';train(parent,cfg(),minutes=1,max_updates=1)
 root=tmp_path/'newflip';start(root,parent/'latest.pt',steps=32,pairs=2,games=4,warmup_updates=0)
 result=json.loads(next(root.glob('flip_result_*.json')).read_text())
 assert result['matches']['games']==4 and result['after']['trials']==4
 assert json.loads((root/'curriculum.json').read_text())['status']=='paused'
 folder=root/'03_trajectory';out=watch(folder,seconds=1,frames=4,headless=True,opponent='self',flip_drills=True)
 metadata=json.loads((out/'metadata.json').read_text());assert metadata['ground_flip_scaffold']
 clip=np.load(out/'frames.npz');np.testing.assert_array_equal(clip['actions'][:,1],NEUTRAL)
 assert not ACTIONS[clip['actions'][:,0],6].any()
 exp=export(folder);assert json.loads((exp/'identity.json').read_text())['action_agreement']==1.


def test_verified_flip_demonstrations_and_warmup_preserve_source_body(tmp_path):
 from duelforge.train import train
 from duelforge.flip_bootstrap import fit,demonstrations
 c=cfg();x,l,a,critical=demonstrations(c,pairs=4)
 assert l[np.arange(len(a)),a].all() and critical.any()
 assert (a==JUMP).any() and (a==DODGE).any() and (a==NEUTRAL).any()
 parent=tmp_path/'source';train(parent,c,minutes=1,max_updates=1)
 identity=sha(parent/'latest.pt');folder=setup(tmp_path/'warm',parent/'latest.pt');before=load(folder/'latest.pt')
 fit(tmp_path/'warm',updates=25);after=load(folder/'latest.pt')
 for key in before['model']:
  if key.startswith(('critic.','actor.0.','actor.1.','actor.3.','actor.4.')):
   torch.testing.assert_close(before['model'][key],after['model'][key],atol=0,rtol=0)
 assert after['learning_transitions']==before['learning_transitions'] and sha(parent/'latest.pt')==identity
 assert load(tmp_path/'warm/flip_warmup_state.pt')['updates']==25

def test_failed_flip_skill_gate_stops_unchanged_continuation(tmp_path,monkeypatch):
 from duelforge.train import train
 import duelforge.train as training
 import duelforge.flip_experiment as experiment
 parent=tmp_path/'source';train(parent,cfg(),minutes=1,max_updates=1)
 root=tmp_path/'flip01';folder=setup(root,parent/'latest.pt')
 (root/'flip_result_1.json').write_text(json.dumps({'candidate_sha256':sha(folder/'latest.pt'),
     'clear_match_regression':False,'after':{'success_rate':0.}}))
 def forbidden(*a,**k):raise AssertionError('Failed unchanged flip trial must not resume')
 monkeypatch.setattr(training,'train',forbidden);monkeypatch.setattr(experiment,'report',lambda root:None)
 experiment.start(root,steps=64)
