import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
import slater_stochastic_benchmark_v0304 as m

def fake(name,side,seed,reg,ot):
    score=2 if name=='u60' else 0
    return {'seed':seed,'side':side,'goals_for':score,'goals_against':0,
            'goal_diff':score,'outcome':1 if score else 0,'draw':not bool(score),
            'decisions':reg,'touches':10,'opponent_touches':9,'kickoffs':1,
            'first_kickoff_signature':'kickoff'+str(seed),'overtime':False,'goal_events':[]}

def test_stochastic_comparison_uses_seed_level_bootstrap():
    res=m.evaluate_stochastic(fake,['original','u60'],3,2,101,10,0)
    assert res['overall']['u60']['matches']==12
    assert res['paired_vs_original']['u60']['win_rate']['num_seed_pairs']==3
    assert res['paired_vs_original']['u60']['goal_diff']['delta']==2


def test_does_not_require_exact_repeated_trajectories():
    calls={}
    def wandering(name,side,seed,reg,ot):
        r=fake(name,side,seed,reg,ot)
        key=(name,side,seed)
        calls[key]=calls.get(key,0)+1
        r['touches']+=calls[key] # stochastic variation is tracked, not rejected
        return r
    res=m.evaluate_stochastic(wandering,['original','u60'],2,2,101,10,0)
    assert len(res['records'])==16


def test_always_rejects_mismatched_start():
    def bad(name,side,seed,reg,ot):
        r=fake(name,side,seed,reg,ot)
        if name=='u60':r['first_kickoff_signature']='bad'
        return r
    with pytest.raises(RuntimeError,match='UNMATCHED_STARTING_STATE'):
        m.evaluate_stochastic(bad,['original','u60'],2,2,101,10,0)


def test_refuse_missing_original():
    with pytest.raises(ValueError):m.evaluate_stochastic(fake,['u60'],2,2,101,10,0)
