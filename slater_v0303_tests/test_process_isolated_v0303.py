from __future__ import annotations
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slater_fullmatch_eval_v0303 as m


def fake_result(policy,side,seed,r,ot):
    win=int(policy=='u60')
    return {'seed':seed,'side':side,'goals_for':win,'goals_against':0,
            'goal_diff':win,'outcome':win,'draw':not win,'decisions':r,
            'touches':10+win,'opponent_touches':9,'kickoffs':1,
            'first_kickoff_signature':'match'+str(seed),'overtime':False,
            'goal_events':[]}


def test_process_orchestration_returns_paired_results():
    report=m.evaluate_processes(['original','u60'],3,100,30,0,fake_result)
    assert len(report['records'])==3*2*2
    assert report['overall']['u60']['wins']==6
    assert report['overall']['original']['wins']==0
    assert report['paired_vs_original']['u60']['goal_diff']['delta']==1


def test_strict_repeat_guard_remains_even_if_goal_score_same():
    a=fake_result('original','blue',100,30,0)
    b=dict(a,touches=a['touches']+1)
    with pytest.raises(RuntimeError,match='NONDETERMINISTIC_ISOLATED_MATCH'):
        m.ensure_same(a,b,'end')


def test_detects_intervening_baseline_drift():
    counts={}
    def drift(policy,side,seed,r,ot):
        row=fake_result(policy,side,seed,r,ot)
        k=(policy,side,seed)
        counts[k]=counts.get(k,0)+1
        if policy=='original' and side=='blue' and seed==100 and counts[k]>=4:
            row['touches']+=1
        return row
    with pytest.raises(RuntimeError,match='after_candidates'):
        m.evaluate_processes(['original','u60'],2,100,30,0,drift)


def test_reject_mismatched_kickoff():
    def incorrect(policy,side,seed,r,ot):
        row=fake_result(policy,side,seed,r,ot)
        if policy=='u60':row['first_kickoff_signature']='different'
        return row
    with pytest.raises(RuntimeError,match='UNMATCHED_KICKOFF'):
        m.evaluate_processes(['original','u60'],2,100,30,0,incorrect)


def test_parse_and_validate_worker_result():
    row=fake_result('original','blue',100,30,0)
    assert m.parse_worker_stdout('warn\n'+m.MARKER+json.dumps(row)+'\n')==row
    with pytest.raises(RuntimeError):m.parse_worker_stdout('not a result')
    with pytest.raises(ValueError):m.parse_worker_stdout(m.MARKER+'{}')


def test_worker_command_does_not_swap_original():
    script=Path('tool.py'); candidate=Path('data/isolated/u60.pt')
    with pytest.raises(ValueError):m.worker_command(script,'original',candidate,'blue',1,10,0)
    with pytest.raises(ValueError):m.worker_command(script,'u60',None,'blue',1,10,0)
    cmd=m.worker_command(script,'u60',candidate,'blue',1,10,0)
    assert '--candidate' in cmd and str(candidate) in cmd and '--worker' in cmd


def test_original_core_comparator_and_fresh_arena_preserved():
    import slater_fullmatch_eval_v0302 as fm
    assert m.fm is fm
    assert fm.match_equal(fake_result('original','blue',5,10,0),fake_result('original','blue',5,10,0))
