import copy
from pathlib import Path
import numpy as np
import pytest
import torch
from nova.triad_selector import Context,SelectorPolicy,SelectorEnv,save_actor,Gate,CONTRACT
from nova.training import load_config
from nova.core import ROOT
from stable_baselines3 import PPO


def settings():
 c=load_config(ROOT/'configs/chronos.json');c.update(workers=1,device='cpu');c['league']['weights']={'scorer':1.}
 c['env'].update(episode_seconds=1,no_touch_seconds=2)
 return c


def test_options_hold_exactly_eight_decisions_and_expose_masks():
 c=Context();x=np.zeros(225,np.float32)
 assert c.observation(x).shape==(234,) and c.observation(x)[-3:].sum()==3
 c.advance(2)
 for _ in range(7):
  np.testing.assert_array_equal(c.observation(x)[-3:],[0,0,1])
  with pytest.raises(ValueError):c.advance(1)
  c.advance(2)
 assert c.observation(x)[-3:].sum()==3


def test_selector_ppo_learns_without_changing_any_expert_and_export_matches(tmp_path,request):
 if not request.config.getoption('--teachers'):pytest.skip('Requires pinned three-model assets')
 torch.set_num_threads(1);env=SelectorEnv(settings())
 try:
  model=PPO(SelectorPolicy,env,n_steps=16,batch_size=16,n_epochs=1,device='cpu',seed=271,
   policy_kwargs=dict(net_arch=dict(pi=[32],vf=[32])))
  obs,_=env.reset(seed=27)
  frozen=[p.detach().clone() for net in (env.teacher.chronos,env.teacher.galactus) for p in net.parameters()]
  before={k:v.clone() for k,v in model.policy.state_dict().items()}
  model.learn(32)
  assert any(not torch.equal(v,before[k]) for k,v in model.policy.state_dict().items())
  after=[p for net in (env.teacher.chronos,env.teacher.galactus) for p in net.parameters()]
  assert all(torch.equal(a,b) and not b.requires_grad for a,b in zip(frozen,after))
  for seed in (27,28):
   obs,_=env.reset(seed=seed)
   for _ in range(12):
    action=int(model.predict(obs,deterministic=False)[0]);assert obs[-3+action]>0
    obs,_,term,trunc,_=env.step(action)
    if term or trunc:break
  path=tmp_path/'selector.pt';save_actor(model,path,'breakout');gate=Gate(path,'breakout')
  obs,_=env.reset(seed=11)
  assert gate.choose(obs[:225])==int(model.predict(obs,deterministic=True)[0])
  with pytest.raises(ValueError,match='hitbox'):Gate(path,'octane')
 finally:env.close()


def test_physics_uses_native_opponent_bodies(cfg):
 from nova.environment import ArenaEnv
 from rlgym.rocket_league.common_values import OCTANE,BREAKOUT
 cfg['env']['learner_hitbox']='breakout'
 # Scripted avoids downloads; native name routing is checked with a frozen stub.
 import nova.environment as module
 from nova.teachers import Scripted
 from unittest.mock import patch
 with patch.object(module,'make_opponent',lambda *a:Scripted()):
  for opponent,expected in [('chronos',BREAKOUT),('galactus',OCTANE),('ripple',OCTANE)]:
   env=ArenaEnv(cfg,opponent=opponent)
   try:
    env.reset(seed=27)
    assert env.state.cars[env.agent].hitbox_type==BREAKOUT
    assert env.state.cars[env.other].hitbox_type==expected
   finally:env.close()


def test_export_launchers_work_without_a_new_venv_and_record_fixed_body(tmp_path):
 import sys,tomllib
 from nova.triad_boot import write_launchers
 write_launchers(tmp_path,sys.executable,'test/triad')
 main=tomllib.loads((tmp_path/'bot.bot.toml').read_text())['settings']
 portable=tomllib.loads((tmp_path/'bot.portable.bot.toml').read_text())['settings']
 assert sys.executable in main['run_command_linux'] and '.venv' in portable['run_command_linux']
 assert main['agent_id']!=portable['agent_id']
 assert tomllib.loads((tmp_path/main['loadout_file']).read_text())['blue_loadout']['car_id']==22
 assert tomllib.loads((tmp_path/'loadout.octane.toml').read_text())['blue_loadout']['car_id']==23


def test_selector_guard_stops_after_large_confirmed_drop(tmp_path,monkeypatch):
 import nova.triad_selector as module
 import nova.chronos_league as league
 from types import SimpleNamespace as NS
 rows=[];old=[]
 for seed in range(12):
  for side in (0,1):
   r=dict(opponent='chronos',scenario='match',seed=seed,side=side,outcome=0,goals_for=0,goals_against=0)
   old.append(r);rows.append(dict(r,outcome=-1,goals_against=1))
 monkeypatch.setattr(module,'Runner',lambda *a:None)
 monkeypatch.setattr(league,'match_suite',lambda *a:(rows,old))
 model=NS(num_timesteps=131072);state={}
 module.check_progress(tmp_path,settings(),model,state)
 assert (tmp_path/'STOP').exists() and model.selector_halt
 assert state['decision']=='regressed'
