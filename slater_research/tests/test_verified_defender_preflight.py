"""Preflight parity contract, pure Python fake physics engine."""
from slater_research.tests.test_verified_defender_env import sample,FakeEngine
from slater_research.verified_defender_preflight import (compare_results,preflight_candidate)


def test_preflight_parity_reproduces_attacker_goal():
    clip,meta=sample()
    made=[]
    def factory():
        engine=FakeEngine();made.append(engine);return engine
    result=preflight_candidate(clip,meta,engine_factory=factory)
    assert result['same_as_v017'] and result['baseline_fidelity_pass']
    assert result['ready_for_counterfactual_investigation']
    assert result['new_goal_status']=='attacker_goal'
    assert all(e.closed for e in made) and len(made)==2


def test_divergent_goal_not_accepted_even_when_error_near():
    from slater_research.verified_defender_env import EpisodeResult
    baseline={'attacker_scored':True,'defender_scored':False,'goal_step':4,
              'endpoint_error_uu':10,'peak_reference_error_uu':20,
              'baseline_fidelity_pass':True}
    new=EpisodeResult('no_goal_by_deadline',False,False,None,3,None,10,20,False)
    result=compare_results(baseline,new)
    assert not result['same_as_v017']


def test_preflight_handles_float_error_tolerance():
    from slater_research.verified_defender_env import EpisodeResult
    base={'attacker_scored':True,'defender_scored':False,'goal_step':4,
          'endpoint_error_uu':10.0,'peak_reference_error_uu':20.0,
          'baseline_fidelity_pass':True}
    new=EpisodeResult('attacker_goal',True,False,4,3,8/120,10.1,20.0,False)
    assert not compare_results(base,new)['same_as_v017']
    new=EpisodeResult('attacker_goal',True,False,4,3,8/120,10.01,20.0,False)
    assert compare_results(base,new)['same_as_v017']
