from pathlib import Path
import torch
import slater_team_campaign as campaign
from slater_v041_core import atomic_json,read_json,sha256
from slater_mechanics_eval import load_actor

ROOT=Path(__file__).resolve().parents[1]


def test_current_check_chooses_candidate_not_rollback_resume(tmp_path,monkeypatch):
    monkeypatch.setattr(campaign,'ROOT',tmp_path)
    folder=tmp_path/'data/isolated/versatile/continue_test';folder.mkdir(parents=True)
    candidate=tmp_path/'trained.pt';candidate.write_bytes(b'trained')
    baseline=tmp_path/'baseline.pt';baseline.write_bytes(b'baseline')
    rollback=tmp_path/'resume.pt';rollback.write_bytes(b'baseline')
    atomic_json(folder/'progress.json',{'candidate':str(candidate),'candidate_sha':sha256(candidate),
        'latest':str(rollback),'latest_sha':sha256(rollback)})
    atomic_json(folder/'protocol.json',{'source':{'path':str(baseline),'sha256':sha256(baseline)}})
    assert campaign.current_pair('continue_test')==(candidate,baseline)


def test_real_team_training_resume_and_source_protection(tmp_path,monkeypatch):
    monkeypatch.setattr(campaign,'BASE',tmp_path)
    source=ROOT/'vendor/nexto/nexto-model.pt';digest=sha256(source)
    cfg={'n_envs':2,'steps_per_env':8,'updates':1,'check_every':1,'minibatch':16,
         'episode_seconds':.2,'screen_seconds':.2,'screen_seeds':1}
    original=campaign.evaluate
    monkeypatch.setattr(campaign,'evaluate',lambda *a,**k:(_ for _ in ()).throw(campaign.EvaluationPaused()))
    campaign.train('pause_resume',source,cfg)
    folder=tmp_path/'pause_resume';state=read_json(folder/'progress.json')
    assert state['status']=='PAUSED' and state['updates']==1 and state['phase']=='evaluation'
    checkpoint=Path(state['latest']);checkpoint_sha=sha256(checkpoint)
    initial=torch.load(folder/'initial.pt',weights_only=True)['actor']
    original_weights=load_actor(ROOT,source).state_dict()
    assert all(torch.equal(initial[k],v) for k,v in original_weights.items())
    monkeypatch.setattr(campaign,'evaluate',original)
    campaign.train('pause_resume')
    state=read_json(folder/'progress.json')
    assert state['status']=='FINITE_EXPERIMENT_COMPLETE' and state['updates']==1
    assert sha256(checkpoint)==checkpoint_sha and sha256(source)==digest
    report=read_json(state['checks'][0]['report'])
    assert report['done'] and len(report['records'])==9*2*2
    assert report['summary']['promoted'] is False
    assert state['playing_model']==str(source)
