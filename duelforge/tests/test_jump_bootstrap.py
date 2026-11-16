import copy
import numpy as np
import torch
from duelforge.runtime import config,save,load,sha
from duelforge.model import ActorCritic
from duelforge.train import train
from duelforge.observation import ACTIONS
from duelforge import jump_bootstrap as jump

def cfg():
 c=config();c.update(n_envs=4,width=32,device='cpu',torch_threads=1)
 c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
 return c

def test_teacher_demonstrations_are_real_successful_legal_contacts():
 x,l,a=jump.demonstrations(cfg(),n=16,seed=713)
 assert len(x)>40 and x.shape[1]==109 and np.isfinite(x).all()
 assert l[np.arange(len(a)),a].all()
 assert (ACTIONS[a,5]>.5).any() and (ACTIONS[a,5]<.5).any()

def test_head_warmup_retains_critic_frozen_body_and_source_checkpoint(tmp_path):
 c=cfg();parent=tmp_path/'parent';train(parent,c,minutes=1,max_updates=1)
 ck=load(parent/'latest.pt');ck['model']['actor.9.bias'][torch.from_numpy(ACTIONS[:,5]>.5)]-=8
 save(parent/'latest.pt',ck);identity=sha(parent/'latest.pt');root=tmp_path/'jump01'
 folder=jump.prepare(root,parent/'latest.pt')
 jump.fit(root,updates=25)
 child=load(folder/'latest.pt')
 assert child['learning_transitions']==ck['learning_transitions']
 assert (root/'bootstrap_state.pt').is_file() and (root/'bootstrap_data.npz').is_file()
 for k in ck['model']:
  if k.startswith(('critic.','actor.0.','actor.1.','actor.3.','actor.4.')):
   torch.testing.assert_close(ck['model'][k],child['model'][k],atol=0,rtol=0)
 assert sha(parent/'latest.pt')==identity and sha(root/'baseline.pt')==identity
 # Resume uses the completed supervised update counter, not RL transitions.
 jump.fit(root,updates=25)
 assert load(root/'bootstrap_state.pt')['updates']==25

def test_candidate_save_clears_only_changed_actor_optimizer_moments(tmp_path):
 c=cfg();parent=tmp_path/'p';train(parent,c,minutes=1,max_updates=1)
 ck=load(parent/'latest.pt');m=ActorCritic(32);m.load_state_dict(ck['model'])
 names=[n for n,_ in m.named_parameters()];ids=[i for g in ck['optimizer']['param_groups'] for i in g['params']]
 out=tmp_path/'out';out.mkdir();jump.save_candidate(out,ck,m,25,.01);child=load(out/'latest.pt')
 for name,index in zip(names,ids):
  if name.startswith(('actor.6.','actor.7.','actor.9.')):assert index not in child['optimizer']['state']
  else:torch.testing.assert_close(ck['optimizer']['state'][index]['exp_avg'],child['optimizer']['state'][index]['exp_avg'],atol=0,rtol=0)
 assert child['jump_bootstrap_updates']==25

def test_failed_air_trial_is_not_blindly_repeated(tmp_path,monkeypatch):
 import json
 from duelforge import air_experiment
 import duelforge.train as training
 root=tmp_path/'air01';folder=root/'03_trajectory';folder.mkdir(parents=True)
 (root/'baseline.pt').write_bytes(b'source');(folder/'latest.pt').write_bytes(b'candidate')
 state={'version':'air-contact-v1','source_sha256':sha(root/'baseline.pt'),'status':'paused'}
 (root/'curriculum.json').write_text(json.dumps(state))
 (root/'air_result_1.json').write_text(json.dumps({'after':{'checkpoint_sha256':sha(folder/'latest.pt'),
     'elevated_contact_rate':0.,'jump_used_rate':0.}}))
 def forbidden(*a,**kw):raise AssertionError('Failed air trial must not resume')
 monkeypatch.setattr(training,'train',forbidden);monkeypatch.setattr(air_experiment,'report',lambda root:None)
 out=air_experiment.start(root)
 assert out['status']=='air_recovery_failed_jump_gate'
