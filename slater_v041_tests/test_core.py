import copy
import json
from pathlib import Path
import pytest
import torch
from slater_v041_core import (DEFAULT_CONFIG,RIVAL_NAMES,find_model,validate_config,
    paired_scores,should_promote,sha256,atomic_json,specs_for_generation,process_lock,training_mode_index)
from slater_v041_overnight import mutate_from,find_latest_trial_checkpoint,write_checkpoint


def test_config_valid():
    assert validate_config(copy.deepcopy(DEFAULT_CONFIG))['run_name']=='overnight01'

def test_unsafe_mutations_rejected():
    v=copy.deepcopy(DEFAULT_CONFIG);v['large_mutation']=1
    with pytest.raises(ValueError):validate_config(v)

def test_saves_mandatory():
    v=copy.deepcopy(DEFAULT_CONFIG);v['save_every_update']=False
    with pytest.raises(ValueError):validate_config(v)

def test_full_opponent_set():
    assert len(RIVAL_NAMES)==6

def test_rlbot_exports_auto_discovered(tmp_path):
    for name in ('wavedash','Original-Champion','V70','Cycle9','V60','Nexto'):
        p=tmp_path/'data'/'rlbot_exports'/name/'nexto-model.pt'
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'mock')
    assert find_model(tmp_path,'wavedash').parts[-2:] == ('wavedash','nexto-model.pt')
    assert find_model(tmp_path,'original_champion').parts[-2:] == ('Original-Champion','nexto-model.pt')
    assert find_model(tmp_path,'v70').parts[-2:] == ('V70','nexto-model.pt')

def test_duplicate_exports_fail(tmp_path):
    for name in ('V70','u70'):
        p=tmp_path/'data'/'rlbot_exports'/name/'nexto-model.pt';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
    with pytest.raises(RuntimeError,match='Ambiguous'):find_model(tmp_path,'v70')

def test_path_override(tmp_path):
    p=tmp_path/'data'/'rlbot_exports'/'wavedash'/'nexto-model.pt';p.parent.mkdir(parents=True);p.write_bytes(b'x')
    assert find_model(tmp_path,'wavedash',str(p))==p

def test_no_ambiguous_unknown_champion(tmp_path):
    with pytest.raises(FileNotFoundError):find_model(tmp_path,'original_champion')

def test_selection_pair_mathematics():
    rows=[{'rival':n,'seed':1,'side':'blue','candidate_outcome':1,'leader_outcome':-1} for n in RIVAL_NAMES]
    summary=paired_scores(rows)
    assert summary['mean_paired_delta']==2.0
    assert should_promote(summary,margin=.1,min_resolved=6)[0]

def test_zero_outcomes_not_wins():
    rows=[{'rival':'v60','seed':1,'side':'blue','candidate_outcome':0,'leader_outcome':0}]
    s=paired_scores(rows)
    assert s['candidate']['wins']==0 and s['candidate']['censored_timeouts']==1
    assert not should_promote(s,margin=.1,min_resolved=1)[0]

def test_core_regression_guard():
    rows=[{'rival':n,'seed':1,'side':'blue',
           'candidate_outcome':-1 if n=='cycle9' else 1,
           'leader_outcome':1 if n=='cycle9' else -1} for n in RIVAL_NAMES]
    s=paired_scores(rows)
    assert not should_promote(s,margin=.1,min_resolved=6)[0]

def test_pair_duplicates_rejected():
    a={'rival':'v60','seed':1,'side':'blue','candidate_outcome':1,'leader_outcome':-1}
    with pytest.raises(ValueError):paired_scores([a,a])

def test_generation_structure():
    assert len(specs_for_generation(1,0))==5
    assert len(specs_for_generation(2,1))==6

def test_atomic_json_and_hash(tmp_path):
    p=tmp_path/'state.json';atomic_json(p,{'ok':True});atomic_json(p,{'ok':False})
    assert json.loads(p.read_text())=={'ok':False}
    assert len(sha256(p))==64

def test_os_lock(tmp_path):
    with process_lock(tmp_path/'lock'):
        with pytest.raises(RuntimeError):
            with process_lock(tmp_path/'lock'):pass

def _dummy_checkpoint():
    x={'w':torch.ones((64,32)),'b':torch.randn((32,)),'w2':torch.randn((32,32)),'b2':torch.randn((32,)),'tiny':torch.tensor(5.)}
    return {'actor':x,'critic':{'w':torch.ones(3)},
            'actor_optimizer':{'state':{'x':'old'},'param_groups':[]},
            'critic_optimizer':{'state':{},'param_groups':[]},
            'global_updates':70,'meta':{'nexto_sha':'abc'},'stage':'slater_v037'}

def test_checkpoint_is_atomic(tmp_path):
    p=tmp_path/'s.pt';write_checkpoint(p,_dummy_checkpoint())
    with pytest.raises(FileExistsError):write_checkpoint(p,_dummy_checkpoint())

def test_small_mutation_is_deterministic_and_stable(tmp_path):
    source=tmp_path/'src.pt';write_checkpoint(source,_dummy_checkpoint())
    a=tmp_path/'a.pt';b=tmp_path/'b.pt'
    info=mutate_from(source,a,.012,1234);mutate_from(source,b,.012,1234)
    x=torch.load(a,weights_only=True);y=torch.load(b,weights_only=True);z=torch.load(source,weights_only=True)
    assert info['tensors_changed']==4
    assert x['actor_optimizer']['state']=={}
    assert torch.equal(x['actor']['w'],y['actor']['w'])
    assert not torch.equal(x['actor']['w'],z['actor']['w'])
    assert torch.equal(x['critic']['w'],z['critic']['w'])
    relative=(x['actor']['w']-z['actor']['w']).square().mean().sqrt().item()
    assert 0.005 < relative < 0.025

def test_large_mutation_more_distant(tmp_path):
    source=tmp_path/'src.pt';write_checkpoint(source,_dummy_checkpoint())
    small=tmp_path/'s.pt';large=tmp_path/'l.pt'
    mutate_from(source,small,.012,13);mutate_from(source,large,.065,13)
    x=torch.load(small,weights_only=True)['actor']['w'];y=torch.load(large,weights_only=True)['actor']['w'];z=torch.load(source,weights_only=True)['actor']['w']
    assert torch.norm(y-z) > 4*torch.norm(x-z)

def test_valid_pt_recovers_without_json(tmp_path):
    x=_dummy_checkpoint();x['global_updates']=73
    p=tmp_path/'g00001_large_root_u0073.pt';write_checkpoint(p,x)
    assert find_latest_trial_checkpoint(tmp_path,'g00001_large_root')==p
    assert json.loads(p.with_suffix('.json').read_text())['recovered_after_crash']

def test_partial_files_ignored(tmp_path):
    (tmp_path/'g00001_large_root_u0074.pt.incomplete').write_bytes(b'oops')
    assert find_latest_trial_checkpoint(tmp_path,'g00001_large_root') is None


def test_training_rotation_covers_every_opponent():
    for offset in range(7):
        assert sorted(training_mode_index(7,episode,offset) for episode in range(1,8))==list(range(7))


def test_rotation_rejects_invalid_episode_index():
    with pytest.raises(ValueError):training_mode_index(7,0,0)


def test_corrupt_full_checkpoint_is_not_resumed(tmp_path):
    a=_dummy_checkpoint();a['global_updates']=72
    good=tmp_path/'g00001_large_root_u0072.pt';write_checkpoint(good,a)
    bad=tmp_path/'g00001_large_root_u0073.pt';bad.write_bytes(b'bad checkpoint')
    bad.with_suffix('.json').write_text('{"fake": true}')
    assert find_latest_trial_checkpoint(tmp_path,'g00001_large_root')==good
