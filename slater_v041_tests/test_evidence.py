import copy
import json

import pytest
import torch

from slater_v041_core import (DEFAULT_CONFIG, RIVAL_NAMES, paired_scores,
                              promotion_alpha, should_promote, validate_config,
                              holdout_seed_count,evaluation_seed_base)
from slater_v041_overnight import check_eval_report, specs_for_generation
import slater_v041_overnight as league


def pairs(deltas):
    return [{'rival':rival,'side':side,'seed':seed,
             'candidate_outcome':delta,'leader_outcome':0}
            for seed,delta in enumerate(deltas)
            for rival in RIVAL_NAMES for side in ('blue','orange')]


def test_small_lucky_holdout_cannot_promote():
    result=paired_scores(pairs([1,1,1]))
    assert result['mean_paired_delta']==1
    assert not should_promote(result,margin=.13,min_resolved=10)[0]


def test_seed_cluster_is_one_observation_not_twelve():
    result=paired_scores(pairs([1]*8))
    evidence=result['seed_evidence']
    assert evidence['seed_count']==8
    assert evidence['sign_test_p_value']==pytest.approx(2**-8)
    assert should_promote(result,margin=.13,min_resolved=10,
                          alpha=promotion_alpha(1))[0]


def test_same_mean_with_inconsistent_seed_results_is_rejected():
    result=paired_scores(pairs([1]*10+[-1]*6))
    assert result['mean_paired_delta']==.25
    assert should_promote(result,margin=.13,min_resolved=10,
                          alpha=promotion_alpha(1))[1]=='advantage_not_consistent_across_seeds'


def test_ties_supply_no_positive_evidence():
    result=paired_scores(pairs([1]*3+[0]*13))
    assert result['seed_evidence']['tied_seeds']==13
    assert not should_promote(result,margin=.13,min_resolved=10)[0]


def test_missing_side_fails_closed_even_with_large_advantage():
    result=paired_scores([r for r in pairs([1]*16) if r['side']=='blue'])
    assert should_promote(result,margin=.13,min_resolved=10)[1]=='incomplete_balanced_holdout'


def test_unknown_opponent_and_wrong_timeout_rejected():
    rows=pairs([1]*8)
    rows[0]['rival']='wrong'
    with pytest.raises(ValueError):paired_scores(rows)
    rows=pairs([1]*8)
    rows[0]['candidate_timeout']=True
    with pytest.raises(ValueError,match='Timeout'):paired_scores(rows)


def test_error_budget_covers_repeated_generations_and_two_finalists():
    assert promotion_alpha(1)==pytest.approx(.0125)
    assert 2*sum(promotion_alpha(g) for g in range(1,1001))<.05
    with pytest.raises(ValueError):promotion_alpha(0)


def test_late_generations_can_still_clear_the_evidence_threshold():
    for generation in (1,40,1000,8000):
        count=holdout_seed_count(16,generation)
        result=paired_scores(pairs([1]*count))
        assert count<=128
        assert should_promote(result,margin=.13,min_resolved=10,
                              alpha=promotion_alpha(generation))[0]


def test_evaluation_seed_ranges_never_reuse_other_phases_or_generations():
    seen=set()
    for generation in range(1,101):
        for holdout in (False,True):
            start=evaluation_seed_base(generation,holdout)
            seeds={start+997*i for i in range(128)}
            assert not (seen & seeds)
            seen.update(seeds)
    with pytest.raises(ValueError,match='exhausted'):evaluation_seed_base(10000,True)


def test_ppo_control_keeps_trial_budget():
    specs=specs_for_generation(1,0)
    assert specs[0]=={'kind':'ppo_continuation','base':'leader'}
    assert len(specs)==5
    assert len(specs_for_generation(2,1))==6


def test_ppo_branch_copies_actor_and_optimizer_without_mutating_source(tmp_path,monkeypatch):
    source=tmp_path/'data/isolated/source.pt'
    source.parent.mkdir(parents=True)
    doc={'actor':{'weight':torch.arange(8.)},'critic':{'weight':torch.ones(8)},
         'actor_optimizer':{'state':{0:{'exp_avg':torch.arange(8.)}},'param_groups':[]},
         'critic_optimizer':{'state':{},'param_groups':[]},'global_updates':70}
    torch.save(doc,source);source_bytes=source.read_bytes()
    config=copy.deepcopy(DEFAULT_CONFIG)
    run_dir=tmp_path/'data/isolated/v041_overnight/test'
    def fake_worker(root,argv,log):
        seed=root/argv[argv.index('--source')+1]
        loaded=torch.load(seed,weights_only=True)
        assert torch.equal(loaded['actor']['weight'],doc['actor']['weight'])
        assert torch.equal(loaded['actor_optimizer']['state'][0]['exp_avg'],
                           doc['actor_optimizer']['state'][0]['exp_avg'])
        assert '--rlbot-delay' in argv and 'mixed_ground' in argv
        loaded['global_updates']=73
        output=root/argv[argv.index('--output-dir')+1]/'g00001_ppo_continuation_u0073.pt'
        league.write_checkpoint(output,loaded)
    monkeypatch.setattr(league,'run_subprocess',fake_worker)
    spec={'kind':'ppo_continuation','base':'leader'}
    result=league.train_branch(tmp_path,config,tmp_path/'manifest.json',1,spec,
                               source,None,None,run_dir)
    assert result.name=='g00001_ppo_continuation_u0073.pt'
    assert source.read_bytes()==source_bytes
    # A finished trial is reused on resume, rather than copied or trained again.
    assert league.train_branch(tmp_path,config,tmp_path/'manifest.json',1,spec,
                               source,None,None,run_dir)==result


@pytest.mark.parametrize('key,value', [('target_kl',float('nan')),
    ('target_kl',0),('promotion_error_budget',1),('generation_candidates_limit',9)])
def test_invalid_stability_settings_rejected(key,value):
    config=copy.deepcopy(DEFAULT_CONFIG);config[key]=value
    with pytest.raises(ValueError):validate_config(config)


def test_cached_report_recomputed_and_bound_to_evaluation(tmp_path):
    rows=pairs([1]*8)
    doc={'candidate_sha':'c','leader_sha':'l','manifest_sha':'m','result':{
        'summary':{'mean_paired_delta':-999},'records':rows,
        'seed_base':0,'seeds':8,'episode_steps':600}}
    # Evaluation seeds increment by 997; convert synthetic seed indices.
    for row in rows:row['seed']*=997
    path=tmp_path/'report.json';path.write_text(json.dumps(doc))
    expected={'manifest_sha':'m','seed_base':0,'seeds':8,'episode_steps':600}
    assert check_eval_report(path,'c','l',expected=expected)['mean_paired_delta']==1
    with pytest.raises(RuntimeError,match='manifest_sha'):
        check_eval_report(path,'c','l',expected=dict(expected,manifest_sha='other'))
    rows.pop();path.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError,match='Incomplete'):
        check_eval_report(path,'c','l',expected=expected)
