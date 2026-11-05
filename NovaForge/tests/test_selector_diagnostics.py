import json
from types import SimpleNamespace as NS
import zipfile
import numpy as np
import pytest
import torch
from filelock import FileLock
from nova import selector_diagnostics as d
from nova.triad_selector import Context,CONTRACT
from nova.core import ROOT,atomic_json,write_model_meta
from nova.training import load_config


def network(logits):
    return lambda x:torch.tensor([logits],dtype=torch.float32)


def test_free_probabilities_do_not_mistake_commitment_for_policy_confidence():
    gate=NS(context=Context(),network=network([.01,0,0]));audit=d.Audit(network([1,0,0]))
    x=np.zeros(225,np.float32);audit.observe(gate,x,'chronos');gate.context.advance(0)
    for _ in range(7):audit.observe(gate,x,'chronos');gate.context.advance(0)
    stats=audit.summary()
    assert stats['latest']['free_choices']==1 and stats['forced_decisions_excluded']==7
    assert stats['latest']['probability_mean']['chronos']==pytest.approx(.33555925)
    assert stats['latest']['mean_top_two_margin']<.004
    assert stats['initial_on_same_latest_visited_contexts']['probability_mean']['chronos']>.57
    assert stats['latest']['mean_entropy_nats']>1.09
    assert stats['latest']['mean_kl_to_initial']>0


def fake_match(cfg,policy,opponent,side,seed,seconds,stop_path,progress):
    assert torch.get_num_threads()==1
    body=cfg['env']['learner_hitbox']
    return dict(opponent=opponent,scenario='match',side=side,seed=seed,seconds=seconds,
        outcome=0,goals_for=0,goals_against=0,initial_observation_sha256=body)


def make_run(tmp_path,monkeypatch):
    import nova.triad_selector as selector
    import nova.chronos_fusion as fusion
    monkeypatch.setattr(selector,'RUNS',tmp_path)
    run=tmp_path/'selector01';run.mkdir();atomic_json(run/'config.json',load_config(ROOT/'configs/chronos.json'))
    for name,step in [('latest.pt',512),('initial.pt',0),('champion.pt',0),('full.zip',512)]:
        p=run/name;p.write_bytes(name.encode());write_model_meta(p,contract=CONTRACT,timesteps=step)
    monkeypatch.setattr(d,'DiagnosticRunner',lambda *a:NS(counts=np.array([120,0,0]),audit=NS(summary=lambda:dict(latest={},forced_decisions_excluded=0))))
    monkeypatch.setattr(fusion,'TeacherFusion',lambda:NS())
    monkeypatch.setattr(d,'play_match',fake_match)
    return run


def test_complete_diagnostics_pair_bodies_and_keep_weights_and_prior_results(tmp_path,monkeypatch):
    run=make_run(tmp_path,monkeypatch);before=d.protected_hashes(run)
    (run/'wdl.json').write_text('previous complete validation')
    path=d.diagnose(seconds=1)
    assert before==d.protected_hashes(run) and (run/'wdl.json').read_text()=='previous complete validation'
    with zipfile.ZipFile(path) as z:
        report=json.loads(z.read('diagnostic.json'))
        assert set(z.namelist())=={'diagnostic.json','README.txt'}
        assert report['protected_run_files_unchanged']
        assert len(report['conditions'])==6
        assert all(len(rows)==8 for rows in report['trials'].values())
        assert len(report['paired_vs_fixed_chronos_same_body'])==3
        assert set(report['reference_body_effects'])=={'galactus_reference_body','ripple_reference_body'}


def test_cancellation_and_busy_training_do_not_replace_a_completed_diagnostic(tmp_path,monkeypatch,capsys):
    run=make_run(tmp_path,monkeypatch)
    (run/'diagnostics').mkdir();(run/'diagnostics/latest.json').write_text('previous')
    def interrupt(*a,**kw):raise KeyboardInterrupt()
    monkeypatch.setattr(d,'play_match',interrupt)
    assert d.diagnose(seconds=1) is None
    assert (run/'diagnostics/latest.json').read_text()=='previous'
    assert 'DIAGNOSTIC_CANCELLED' in capsys.readouterr().out
    with FileLock(str(run/'train.lock')):
        with pytest.raises(RuntimeError,match='launcher 8'):d.diagnose(seconds=1)


def test_same_body_pairing_guard_detects_different_starts(tmp_path,monkeypatch):
    torch.set_num_threads(1)
    calls=[0]
    def mismatch(*a,**kw):
        r=fake_match(*a,**kw);calls[0]+=1;r['initial_observation_sha256']=str(calls[0]);return r
    monkeypatch.setattr(d,'play_match',mismatch)
    cells=d.conditions('breakout',False)
    with pytest.raises(RuntimeError,match='same hitbox'):
        d.benchmark(load_config(ROOT/'configs/chronos.json'),cells,{c['label']:None for c in cells},1,1,tmp_path/'STOP')
