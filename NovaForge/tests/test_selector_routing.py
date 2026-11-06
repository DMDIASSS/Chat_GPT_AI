import copy
import json
from types import SimpleNamespace as NS
import zipfile
import numpy as np
import pytest
import torch
from nova import selector_routing as r
from nova.triad_selector import Context,NAMES,FOUR_NAMES
from nova.selector_diagnostics import protected_hashes
from test_selector_diagnostics import make_run,fake_match


def fake_runner(names):
    runner=r.SampledRunner.__new__(r.SampledRunner)
    runner.gate=NS(n=len(names),names=names,context=Context(names=names),
        network=lambda x:torch.zeros((1,len(names))))
    runner.counts=np.zeros(len(names),dtype=np.int64)
    runner.teacher=NS(proposals=lambda *a:np.arange(len(names)))
    runner.env=NS(arena=NS(state=None),previous=None,mirror=False)
    return runner


@pytest.mark.parametrize('names',[NAMES,FOUR_NAMES])
def test_samples_only_when_free_holds_eight_and_has_independent_repeatable_rng(names):
    np.random.seed(123);numpy_before=np.random.get_state();torch_before=torch.get_rng_state().clone()
    runner=fake_runner(names);runner.begin_match(451000001,0);obs=np.zeros(315,np.float32)
    choices=[]
    for _ in range(64):
        first=runner.world_controls(obs);choices.append(first)
        stream=copy.deepcopy(runner.rng.bit_generator.state)
        assert [runner.world_controls(obs) for _ in range(7)]==[first]*7
        assert runner.rng.bit_generator.state==stream
    assert len(set(choices))==len(names) and runner.free_counts.sum()==64
    assert runner.counts.sum()==512
    runner.begin_match(451000001,0);runner.gate.context=Context(names=names)
    replay=[runner.world_controls(obs) for _ in range(512)]
    assert replay[::8]==choices
    assert torch.equal(torch.get_rng_state(),torch_before)
    numpy_after=np.random.get_state()
    assert numpy_before[0]==numpy_after[0] and np.array_equal(numpy_before[1],numpy_after[1]) and numpy_before[2:]==numpy_after[2:]
    # Goals reset commitment through inherited bind, without rewinding the sampler.
    runner.teacher.reset=lambda *a:None;runner.env.arena.agent=None
    stream=copy.deepcopy(runner.rng.bit_generator.state)
    runner.gate.reset=lambda:setattr(runner.gate,'context',Context(names=names))
    runner.bind(runner.env)
    assert runner.rng.bit_generator.state==stream


def prepare(tmp_path,monkeypatch):
    run=make_run(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'Runner',lambda *a:NS(gate=NS(fusion_path=None,names=NAMES)))
    monkeypatch.setattr(r,'SampledRunner',lambda *a:NS())
    monkeypatch.setattr(r,'teacher_pool',lambda *a:NS())
    monkeypatch.setattr(r,'play_match',fake_match)
    return run


def test_complete_routing_report_keeps_models_prior_wdl_and_diagnostic(tmp_path,monkeypatch):
    run=prepare(tmp_path,monkeypatch);before=protected_hashes(run)
    (run/'wdl.json').write_text('prior validation')
    (run/'diagnostics').mkdir();(run/'diagnostics/latest.json').write_text('prior diagnostic')
    path=r.evaluate('selector01',pairs=1,seconds=1)
    assert before==protected_hashes(run)
    assert (run/'wdl.json').read_text()=='prior validation'
    assert (run/'diagnostics/latest.json').read_text()=='prior diagnostic'
    with zipfile.ZipFile(path) as z:
        report=json.loads(z.read('routing.json'))
        assert report['seed_start']==451000001 and report['protected_run_files_unchanged']
        assert len(report['trials'])==4 and sum(map(len,report['trials'].values()))==32
        assert report['paired_latest_sampled_vs_initial_sampled']['mean_delta']==0


def test_cancellation_retains_previous_completed_routing(tmp_path,monkeypatch):
    run=prepare(tmp_path,monkeypatch)
    (run/'routing').mkdir();(run/'routing/latest.json').write_text('previous')
    def interrupt(*a,**kw):raise KeyboardInterrupt
    monkeypatch.setattr(r,'play_match',interrupt)
    assert r.evaluate('selector01',seconds=1) is None
    assert (run/'routing/latest.json').read_text()=='previous'


def test_match_setup_called_once_per_game_and_start_guard(tmp_path,monkeypatch):
    calls=[]
    policy=NS(begin_match=lambda seed,side:calls.append((seed,side)),free_counts=np.array([1,0,0]),gate=NS(names=NAMES))
    monkeypatch.setattr(r,'play_match',fake_match)
    cfg={'env':{'learner_hitbox':'breakout'}}
    rows=r.benchmark(cfg,{'sampled':policy},1,1,tmp_path/'STOP')
    assert len(calls)==8 and len(set(calls))==8 and len(rows['sampled'])==8
    def mismatch(*a,**kw):
        out=fake_match(*a,**kw);out['initial_observation_sha256']=str(len(calls));return out
    monkeypatch.setattr(r,'play_match',mismatch)
    with pytest.raises(RuntimeError,match='Different routing starts'):
        r.benchmark(cfg,{'first':None,'sampled':policy},1,1,tmp_path/'STOP')
