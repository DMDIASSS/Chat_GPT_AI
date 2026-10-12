import pytest
from slater_research.car_state_compare import compare, check_pair


def row(mode,ok=True):
    return {'window_s':1.0,'mode':mode,'accepted':ok,'endpoint_position_matched':ok,
            'entire_reference_window_matched':ok,'verified_goal_by_deadline':ok,
            'scored_as_reference_team':ok,'reference_goal_step':5,'start_step':2,
            'post_budget_steps':4,'actual_goal_step':6,
            'max_reference_window_error_uu':1.,'endpoint_ball_error_uu':1.,
            'goal_offset_s':1/15,'early_goal_unverifiable':False,'error':None}


def test_positive_control_retained():
    cand={'clip_file':'x.npz','window_s':1.0,'start_step':2,'reference_goal_step':5,
          'split':'train','replay_sha256':'a'*64}
    case={'file':'x.npz','replay_sha256':'a'*64,'windows':[row('ghosted'),row('all_dynamic')]}
    cat={'candidates':[cand]}
    rep={'schema_version':1,'cases':[{'clip_file':'x.npz','status':'pending_fidelity_revalidation'}]}
    audit={'schema_version':3,'cases':[case]}
    res=compare(cat,rep,audit,audit)
    assert res['summary']['retained_positive_controls']==1
    bad={'schema_version':3,'cases':[{'file':'x.npz','replay_sha256':'a'*64,'windows':[row('ghosted'),row('all_dynamic',False)]}]}
    res=compare(cat,rep,audit,bad)
    assert res['summary']['lost_or_missing_positive_controls']==1
    assert not res['cases'][0]['repaired_baseline_pass']


def test_holdout_rejected_and_demo_not_promoted():
    cand={'clip_file':'x.npz','window_s':1.0,'start_step':2,'reference_goal_step':5,'split':'test','replay_sha256':'a'*64}
    rep={'schema_version':1,'cases':[{'clip_file':'x.npz','status':'pending_fidelity_revalidation'}]}
    audit={'schema_version':3,'cases':[{'file':'x.npz','replay_sha256':'a'*64,'windows':[row('ghosted'),row('all_dynamic')]}]}
    with pytest.raises(ValueError,match='train-split'):
        compare({'candidates':[cand]},rep,audit,audit)
    cand['split']='train'
    rep['cases'][0]['status']='excluded_all_defenders_demoed'
    res=compare({'candidates':[cand]},rep,audit,audit)
    assert res['summary']['retained_positive_controls']==0


def test_window_mode_and_early_score_fail():
    cand={'window_s':1.,'start_step':2,'reference_goal_step':5}
    assert not check_pair({'windows':[row('ghosted')]},cand)[0]
    a=row('ghosted');a['actual_goal_step']=3
    assert not check_pair({'windows':[a,row('all_dynamic')]},cand)[0]
