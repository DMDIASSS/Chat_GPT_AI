import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
import torch
from filelock import FileLock
from nova.core import atomic_json,write_model_meta
from nova.triad_selector import CONTRACT


def make_run(tmp_path,monkeypatch):
 import nova.triad_selector as selector
 from nova.training import load_config
 from nova.core import ROOT
 run=tmp_path/'selector01';run.mkdir()
 cfg=load_config(ROOT/'configs/chronos.json');atomic_json(run/'config.json',cfg)
 for name,step in [('latest.pt',32768),('initial.pt',0)]:
  p=run/name;p.write_bytes(name.encode());write_model_meta(p,contract=CONTRACT,timesteps=step,hitbox='breakout')
 monkeypatch.setattr(selector,'RUNS',tmp_path)
 def runner(*args):
  assert torch.get_num_threads()==1
  return NS(world_controls=lambda obs:None)
 monkeypatch.setattr(selector,'Runner',runner)
 return run


def sample_rows():
 rows=[]
 for side in (0,1):
  rows.append(dict(opponent='chronos',scenario='match',seed=7,side=side,outcome=0,goals_for=0,goals_against=0))
 return rows


def test_manual_evaluation_limits_threads_prints_start_and_records_checkpoint(tmp_path,monkeypatch,capsys):
 import nova.triad_selector as selector
 import nova.chronos_league as league
 run=make_run(tmp_path,monkeypatch);original=torch.get_num_threads()
 try:
  torch.set_num_threads(2)
  monkeypatch.setattr(league,'match_suite',lambda *a:(sample_rows(),sample_rows()))
  selector.evaluate(pairs=1,seconds=1)
  text=capsys.readouterr().out
  assert 'SELECTOR_EVALUATION_START: Torch threads=1' in text
  assert 'LOADING 1/2' in text and 'LOADING 2/2' in text and 'SELECTOR_WDL_READY:' in text
  data=json.loads((run/'wdl.json').read_text());assert data['candidate_timesteps']==32768
  assert data['candidate']['draws']==2 and (run/'latest.pt').read_bytes()==b'latest.pt'
 finally:torch.set_num_threads(original)


def test_cancel_keeps_previous_result_and_weights(tmp_path,monkeypatch,capsys):
 import nova.triad_selector as selector
 import nova.chronos_league as league
 run=make_run(tmp_path,monkeypatch);old=b'previous complete evaluation';(run/'wdl.json').write_bytes(old)
 def interrupt(*args):raise KeyboardInterrupt()
 monkeypatch.setattr(league,'match_suite',interrupt)
 selector.evaluate(pairs=1,seconds=1)
 assert 'EVALUATION_CANCELLED' in capsys.readouterr().out
 assert (run/'wdl.json').read_bytes()==old and (run/'latest.pt').read_bytes()==b'latest.pt'


def test_training_lock_error_gives_pause_instruction(tmp_path,monkeypatch):
 import nova.triad_selector as selector
 run=make_run(tmp_path,monkeypatch)
 with FileLock(str(run/'train.lock')):
  with pytest.raises(RuntimeError,match='launcher 8'):selector.evaluate(pairs=1,seconds=1)


def test_match_suite_prints_start_heartbeat_and_every_game_completion(tmp_path,monkeypatch,capsys):
 import nova.chronos_league as league
 def fake(cfg,policy,opponent,side,seed,seconds,stop_path,progress=None):
  progress(dict(simulated_seconds=.5,seconds=seconds,goals_for=0,goals_against=0,wall_seconds=5))
  return dict(opponent=opponent,side=side,seed=seed,scenario='match',outcome=0,goals_for=0,goals_against=0,initial_observation_sha256='same seeded start')
 monkeypatch.setattr(league,'play_match',fake)
 policy=NS(action=lambda obs:0)
 rows,baseline=league.match_suite({},policy,policy,1,1,7,tmp_path/'STOP')
 text=capsys.readouterr().out
 assert len(rows)==len(baseline)==8
 assert 'WDL_START: 16 games' in text and 'GAME 1/16' in text and 'GAME 16/16' in text
 assert text.count(' START (')==16 and text.count(' DONE score=')==16 and text.count(' RUNNING ')==16
