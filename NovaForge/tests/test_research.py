import copy
import json
from pathlib import Path
import zipfile
import numpy as np
import pytest
from nova.core import ROOT,atomic_json,write_model_meta,sha256
from nova.objectives import REGISTRY,objective,definition
from nova.training import load_config
from nova.triad_selector import CONTRACT
from nova import research


def config():return load_config(ROOT/'configs/chronos.json')


def source(tmp_path,monkeypatch):
    import nova.triad_selector as selector
    monkeypatch.setattr(selector,'RUNS',tmp_path)
    run=tmp_path/'selector01';run.mkdir();atomic_json(run/'config.json',config())
    for name,step in [('full.zip',512),('latest.pt',512),('initial.pt',0),('champion.pt',0)]:
        p=run/name;p.write_bytes(name.encode());write_model_meta(p,contract=CONTRACT,timesteps=step)
    return run


def test_objective_ablation_uses_real_eight_tick_reward_and_timeout_bootstrap():
    from nova.chronos import ChronosEnv
    for name in REGISTRY:
        cfg=config();cfg['objective']=dict(REGISTRY[name]);cfg['env'].update(episode_seconds=8/120,no_touch_seconds=1)
        env=ChronosEnv(cfg,opponent='scorer',scenario='shot',side=0)
        try:
            obs,_=env.reset(seed=27);old=env.arena.potential(env.arena.state)
            obs,reward,term,trunc,info=env.step(int(np.flatnonzero(obs[225:])[0]))
            assert trunc and not term
            assert reward==pytest.approx(cfg['ppo']['gamma']*env.arena.potential(env.arena.state)-old)
            if name=='goals_only':assert reward==0
        finally:env.close()
    for bad in (float('nan'),-1,True,11):
        cfg=config();cfg['objective']=dict(REGISTRY['current'],distance=bad)
        with pytest.raises(ValueError):objective(cfg)


def test_default_objective_preserves_original_formula_and_identity_changes():
    cfg=config();before=definition(cfg)
    assert before['spec']==REGISTRY['current']
    cfg['objective']=dict(REGISTRY['field_only']);assert before['sha256']!=definition(cfg)['sha256']
    cfg['objective']['version']='future-v2'
    with pytest.raises(ValueError):definition(cfg)


def test_fork_preserves_source_optimizer_and_uses_latest_as_local_champion(tmp_path,monkeypatch):
    run=source(tmp_path,monkeypatch);before={p.name:sha256(p) for p in run.iterdir() if p.is_file()}
    dst=research.fork('selector01','no_distance','field_only',17)
    assert (dst/'full.zip').read_bytes()==(run/'full.zip').read_bytes()
    assert (dst/'champion.pt').read_bytes()==(run/'latest.pt').read_bytes()
    assert json.loads((dst/'config.json').read_text())['objective']['distance']==0
    assert before=={p.name:sha256(p) for p in run.iterdir() if p.is_file() and p.name!='train.lock'}
    with pytest.raises(ValueError):research.fork('selector01','selector01')
    with pytest.raises(ValueError):research.fork('selector01','no_distance')
    with pytest.raises(ValueError):research.run_path('../outside')


def test_config_identity_freezes_but_source_and_sessions_are_archived(tmp_path):
    cfg=config();research.session(tmp_path,cfg,512);research.session(tmp_path,cfg,1024)
    assert len(list((tmp_path/'research/sessions').glob('*.json')))==2
    cfg['objective']=dict(REGISTRY['goals_only'])
    with pytest.raises(ValueError,match='research-fork'):research.session(tmp_path,cfg,1024)
    archive=next((tmp_path/'research/source').glob('*.zip'))
    with zipfile.ZipFile(archive) as z:
        assert 'nova/objectives.py' in z.namelist() and z.testzip() is None
        assert not any('/assets/' in n or n.endswith(('.pt','.lt','.onnx')) for n in z.namelist())


def test_evaluation_archives_exact_tested_models_and_marks_reused_seed_bank(tmp_path,monkeypatch):
    run=source(tmp_path,monkeypatch);cfg=config()
    d=dict(candidate_sha256=sha256(run/'latest.pt'),baseline_sha256=sha256(run/'initial.pt'),candidate_timesteps=512)
    out=research.evaluation_record(run,cfg,d,'validation',research.SEED_BANKS['validation'],2,60)
    (run/'latest.pt').write_bytes(b'new later weights')
    assert (out/'latest.pt').read_bytes()==b'latest.pt'
    assert not json.loads((out/'evaluation.json').read_text())['previously_used_seed_bank']
    write_model_meta(run/'latest.pt',contract=CONTRACT,timesteps=1024)
    d.update(candidate_sha256=sha256(run/'latest.pt'),candidate_timesteps=1024)
    second=research.evaluation_record(run,cfg,d,'validation',research.SEED_BANKS['validation'],2,60)
    assert json.loads((second/'evaluation.json').read_text())['previously_used_seed_bank']
    with pytest.raises(ValueError):research.evaluation_record(run,dict(cfg,objective={'invalid':1}),d,'test',1,2,60)
    archive=research.report('selector01')
    with zipfile.ZipFile(archive) as z:
        assert 'objective.json' in z.namelist()
        assert not any(n.endswith(('.pt','.zip','.lt','.log','.csv')) for n in z.namelist())


def test_seed_banks_do_not_overlap_between_roles():
    banks=[{base+op*100000+i for op in range(4) for i in range(100)} for base in research.SEED_BANKS.values()]
    assert all(not a.intersection(b) for i,a in enumerate(banks) for b in banks[i+1:])
