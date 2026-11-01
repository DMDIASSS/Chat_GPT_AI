from copy import deepcopy
import json
from pathlib import Path

import pytest
import slater_model_selection as s
import slater_nexto_goal_benchmark as bench


def rows(outcomes):
    return [dict(id=str(i), seed=100 + i//2, learner_team='blue' if i%2 == 0 else 'orange',
                 goals_for=int(x == 'W'), goals_against=int(x == 'L'),
                 seconds=90 if x == 'D' else 5) for i, x in enumerate(outcomes)]


@pytest.mark.parametrize('outcome,assignment,rate', [('W','WIN',1), ('L','LOSS',0), ('D','DRAW',None)])
def test_streaks_keep_observed_counts_and_assigned_results_separate(outcome, assignment, rate):
    cfg = bench.validate_goal_config({})
    prior = 'LD' if outcome == 'W' else 'WD' if outcome == 'L' else 'WL'
    result = bench.totals(rows(prior + outcome*10), cfg)
    assert result['auto_assigned'] and result['assigned_result'] == assignment
    assert result['assigned_win_rate'] == rate
    assert result['win_rate'] == result['wins'] / result['rounds']
    assert sum(result[k] for k in ('wins','draws','losses')) == 12
    assert result['status'] == 'AUTO_' + assignment + '_STREAK'


def test_draws_count_to_round_budget_and_order_does_not_change_streak():
    cfg = bench.validate_goal_config({})
    data = rows('WLDW' * 10)
    assert bench.totals(data, cfg)['status'] == 'ROUND_BUDGET_COMPLETE'
    assert bench.totals(list(reversed(data)), cfg) == bench.totals(data, cfg)
    assert bench.totals(rows('D'*9), cfg)['status'] == 'EVALUATING'
    assert bench.totals(rows('W'*10), cfg)['status'] == 'AUTO_WIN_STREAK'
    # Statistics for another format do not inherit the auto-result.
    assert bench.totals(rows('WL'*5), cfg)['assigned_result'] is None


@pytest.mark.parametrize('value', [{'rounds_per_format':29}, {'rounds_per_format':41},
    {'early_stop_streak':7}, {'early_stop_streak':13}, {'timeout_seconds':float('nan')},
    {'target_goals':40}, {'formats':['1v1']}])
def test_invalid_settings(value):
    with pytest.raises(ValueError): bench.validate_goal_config(value)


def test_first_goal_record_rejects_premature_draw_and_multi_goal():
    job = {'id':'x', 'seconds':90, 'stop_after_first_goal':True}
    record = {**job, 'seconds':5, 'finish':'COMPLETE', 'goals_for':1, 'goals_against':0,
              'round_end':'FIRST_GOAL'}
    assert s.validate_record(job, record) is record
    bad = {**record, 'goals_for':0, 'round_end':'NO_GOAL_TIMEOUT'}
    with pytest.raises(ValueError): s.validate_record(job, bad)
    with pytest.raises(ValueError): s.validate_record(job, {**record, 'goals_for':2})
    assert s.validate_record(job, {**bad,'seconds':90})


def test_all_candidates_all_formats_resume_and_hash_tampering(tmp_path, monkeypatch):
    run = tmp_path/'run'
    models = {n:{'source_paths':[{'path':n+'.pt','families':['mechanics']}]} for n in ('baseline','candidate')}
    inventory={'candidate_ids':list(models),'models':models,
               'roles':{'baseline':'baseline','rival:nexto':'nexto'}}
    cfg=s.merge_config(s.DEFAULT, {'rivals':{'nexto':str(s.native.DEFAULT_RIVAL)},
                                  'goal_race':{}, 'job_group':6,
                                  'stages':{'screen':{'rivals':['nexto']}}})
    cfg=s.validate_config(cfg)
    protocol={'settings':cfg,'protocol_sha':'a'*64,'identity':{'native':{}},'inventory_sha256':'fixture'}
    def initialize(*args):
        run.mkdir()
        s.atomic_json(run/'config.json',{'settings':cfg})
        s.atomic_json(run/'protocol.json',protocol)
        return run,protocol
    monkeypatch.setattr(s,'run_path',lambda name:run)
    monkeypatch.setattr(s,'initialize',initialize)
    monkeypatch.setattr(s,'verify_run',lambda *args:inventory)
    seen=set()
    def execute(run,protocol,inventory,jobs,wave,build_dir=None):
        receipt=s.read_json(wave.with_suffix('.hashes.json'),{})
        result={}
        for job in jobs:
            assert job['id'] not in seen
            seen.add(job['id'])
            mode=job['format'][0]
            record={**job,'seconds':1 if mode!=3 else 90,'finish':'COMPLETE',
                    'goals_for':int(mode==1),'goals_against':int(mode==2),
                    'round_end':'NO_GOAL_TIMEOUT' if mode==3 else 'FIRST_GOAL'}
            path=run/'cache/records'/(job['id']+'.json')
            s.atomic_json(path,record)
            receipt[job['id']]=s.sha256(path)
            result[job['id']]=record
        s.atomic_json(wave.with_suffix('.hashes.json'),receipt)
        return result
    monkeypatch.setattr(bench,'execute_wave',execute)
    paused=bench.run_benchmark('test',config=cfg,max_games=7)
    assert paused['status']=='GAME_BUDGET_REACHED' and paused['completed_games']==6
    completed=bench.run_benchmark('test',resume=True,max_games=54)
    assert completed['complete'] and completed['completed_games']==60
    assert completed['status']=='GOAL_BENCHMARK_COMPLETE'
    for row in completed['models']:
        assert row['formats']['1v1']['assigned_win_rate']==1
        assert row['formats']['2v2']['assigned_win_rate']==0
        assert row['formats']['3v3']['assigned_result']=='DRAW'
        assert all(m['rounds']==10 for m in row['formats'].values())
    before=len(seen)
    assert bench.run_benchmark('test',resume=True)['complete']
    assert len(seen)==before
    assert (run/'winrates.csv').is_file()
    file=next((run/'cache/records').glob('*.json'))
    file.write_text(file.read_text()+' ')
    with pytest.raises(ValueError,match='changed'):bench.load_ledger(run)
