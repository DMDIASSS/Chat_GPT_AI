import copy,json
from pathlib import Path
import pytest
from duelforge.runtime import sha
from duelforge import match_guard

def result(candidate,parent,winner=True):
    rows=[{'context':'match','pair':p,'color':c,'native_seed':0xC0100000+p,
           'seconds':100.,'goals_for':int(winner),'goals_against':int(not winner),
           'outcome':1 if winner else -1} for p in range(1000) for c in (0,1)]
    return {'candidate_sha256':candidate,'opponent_sha256':parent,'games':rows,
            'contexts':{'match':{}},'candidate_learning_transitions':61_218_305}

def test_qualification_uses_raw_matches_and_exact_identities():
    r=result('candidate','parent');assert match_guard.qualify(r,'candidate','parent')['score_rate']==1
    assert match_guard.qualify(r,'wrong','parent') is None
    r['games']=r['games'][:200];assert match_guard.qualify(r,'candidate','parent') is None
    r=result('candidate','parent');r['games'][1]['native_seed']+=1
    assert match_guard.qualify(r,'candidate','parent') is None
    r=result('candidate','parent');r['games'][0]['seconds']=30
    assert match_guard.qualify(r,'candidate','parent') is None
    assert match_guard.qualify(result('candidate','parent',False),'candidate','parent') is None

def test_confirmed_reference_is_pinned_and_proof_modification_detected(tmp_path):
    root=tmp_path;folder=root/'03_trajectory';folder.mkdir()
    (folder/'latest.pt').write_bytes(b'exact checkpoint with actor Adam and counters')
    (folder/'initial.pt').write_bytes(b'parent')
    identity=sha(folder/'latest.pt');parent=sha(folder/'initial.pt')
    proof=folder/'eval_confirm.json';proof.write_text(json.dumps(result(identity,parent)))
    ref=match_guard.reference(root,folder)
    assert sha(folder/ref['actor_path'])==identity
    assert sha(folder/'latest.pt')==identity
    # Continued training may change latest; it must not change the pinned reference.
    (folder/'latest.pt').write_bytes(b'later experiment')
    assert match_guard.reference(root,folder)['actor_sha256']==identity
    proof.write_text('{}')
    with pytest.raises(ValueError):match_guard.reference(root,folder)

def test_regression_check_uses_fixed_reference_and_pauses_only_when_worse(tmp_path,monkeypatch):
    calls=[]
    def evaluate(folder,**kw):
        calls.append(kw)
        return {'candidate_sha256':'new','overall':{'score_interval_95':[.2,.4],'score_rate':.3}}
    monkeypatch.setattr(match_guard,'evaluate',evaluate)
    ref={'learning_transitions':100,'actor_path':'pins/ref/actor.pt','actor_sha256':'ref'};state={}
    assert not match_guard.check(tmp_path,tmp_path,state,100+4_999_999,ref)
    assert not calls
    assert match_guard.check(tmp_path,tmp_path,state,100+5_000_000,ref)
    assert state['status']=='match_regression_paused'
    assert calls[0]['opponent']==tmp_path/'pins/ref/actor.pt'

def test_match_reference_allows_real_continuation_despite_contact_warning(tmp_path,monkeypatch):
    from duelforge import acquisition_experiment as experiment
    from duelforge.runtime import config,atomic_json
    from duelforge.train import train
    c=config();c.update(width=32,n_envs=4,device='cpu',torch_threads=1)
    c['ppo'].update(steps=8,epochs=1,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**9
    parent=tmp_path/'potential';origin=train(parent,c,minutes=1,max_updates=1)
    root=tmp_path/'contact01';state=experiment.initialize(root,parent)
    state.update(stage_index=2,status='trajectory_gate_failed_paused',probes=['failed.json'])
    atomic_json(root/'failed.json',{'stage':'trajectory','gate_passed':False})
    atomic_json(root/'curriculum.json',state)
    folder=experiment.stage_folder(root,2)
    experiment.fork_stage(parent/'latest.pt',folder,root/'baseline.pt','trajectory',origin)
    monkeypatch.setattr(match_guard,'reference',lambda *args:{'learning_transitions':origin})
    checks=[];monkeypatch.setattr(match_guard,'check',lambda *args:checks.append(args) or False)
    monkeypatch.setattr(experiment,'probe_checkpoint',lambda *a,**kw:{'success_rate':0.,'median_contact_seconds':6.,'raw':{}})
    out=experiment.start(root,parent,steps=64,chunk_steps=64,max_checks=1)
    assert out['status']=='step_budget_saved' and out['contact_skill_warning']
    assert checks and out['checkpoints']['trajectory']['learning_transitions']>origin
