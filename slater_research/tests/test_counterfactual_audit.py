"""Counterfactual probe tests run without RLGym or RocketSim installed."""
from types import SimpleNamespace as NS
import copy
import numpy as np
import pytest

from slater_research.replay_engine import Clip, split_replay
from slater_research.counterfactual_audit import (
    PROBES, select_candidates, defender_controls, validate_candidate,
    simulate, compare_probe, audit_candidate,
)


def chosen_sha(start='1'):
    for i in range(1000):
        sha = f'{i:064x}'
        if split_replay(sha) == start:
            return sha
    raise AssertionError('unreachable')


def candidate(name, sha, start=1, goal=3, distance=300):
    return {'clip_file': name, 'replay_sha256': sha, 'split': split_replay(sha),
            'window_s': 0.5, 'start_step': start, 'reference_goal_step': goal,
            'tail_steps': 2, 'start_min_defender_distance_uu': distance,
            'priority': 'defender_opportunity_candidate'}


def mkclip(sha=None):
    sha = sha or chosen_sha('train')
    def state(i):
        ball = NS(position=np.array([0., 10.*i, 0.]), linear_velocity=np.zeros(3))
        return NS(ball=ball,
                  cars={1:NS(is_orange=False), 2:NS(is_orange=True)},
                  goal_scored=False)
    controls=np.zeros((4,2,8), dtype=np.float32)
    controls[:,0,0]=1
    return Clip([state(i) for i in range(4)], controls, (1,2),1,3,sha)


class FakeEngine:
    def __init__(self): self.state=None; self.closed=False
    def set_state(self,state,shared):
        self.state=copy.deepcopy(state)
        return self.state
    def step(self,commands,shared):
        # For unit tests, a reversing defender intercepts the ball.
        speed = 0 if commands[2][0,0] == -1 else 10
        self.state.ball.position[1]+=speed
        self.state.goal_scored = self.state.ball.position[1]>=40
        return self.state
    def close(self):self.closed=True


def test_policy_vectors_are_8_dimensional_and_safe():
    x=np.ones(8,dtype=np.float32)
    assert all(defender_controls(p,x,first=True).shape==(8,) for p in PROBES)
    assert np.array_equal(defender_controls('replay',x,first=False),x)
    assert defender_controls('neutral',x,first=False).sum()==0
    assert defender_controls('brake',x,first=False)[0]==-1
    assert defender_controls('boost_straight',x,first=False)[6]==1
    assert defender_controls('jump_boost',x,first=True)[5]==1
    assert defender_controls('jump_boost',x,first=False)[5]==0
    with pytest.raises(ValueError):defender_controls('invalid',x,first=True)


def test_select_candidates_round_robins_by_match_and_preserves_split():
    s1=chosen_sha('train')
    s2=next(f'{i:064x}' for i in range(2000) if f'{i:064x}' != s1 and split_replay(f'{i:064x}')=='train')
    a=candidate('a.npz',s1);b=candidate('b.npz',s1)
    c=candidate('c.npz',s2)
    catalog={'schema_version':1,'candidates':[a,b,c]}
    selected=select_candidates(catalog,limit=2)
    assert {x['replay_sha256'] for x in selected} == {s1,s2}
    assert len(select_candidates(catalog,limit=3))==3
    b['clip_file']='../bad.npz'
    with pytest.raises(ValueError,match='filename'):select_candidates(catalog)


def test_validate_candidate_mismatch_and_defenders():
    clip=mkclip();c=candidate('test.npz',clip.replay_sha)
    assert validate_candidate(c,clip)[3] == (2,)
    c['reference_goal_step']=2
    with pytest.raises(ValueError,match='reference window'):validate_candidate(c,clip)


def test_positive_control_goal_tail_and_counterfactual_changes_outcome():
    clip=mkclip();c=candidate('goal.npz',clip.replay_sha)
    baseline=simulate(clip,c,'replay',engine=FakeEngine())
    assert baseline['baseline_fidelity_pass']
    assert baseline['goal_step']==4 and baseline['endpoint_error_uu']==0
    assert baseline['attacker_scored']
    intervention=simulate(clip,c,'brake',engine=FakeEngine())
    assert not intervention['attacker_scored']
    compare=compare_probe(baseline,intervention)
    assert compare['goal_outcome_changed_by_deadline']
    assert compare['interpretation']=='attacker_goal_not_observed_by_deadline'
    assert intervention['endpoint_ball_xyz'] is not None


def test_probe_evaluation_requires_baseline_and_closes_engines():
    clip=mkclip();c=candidate('goal.npz',clip.replay_sha)
    made=[]
    def factory():
        eng=FakeEngine();made.append(eng);return eng
    result=audit_candidate(c,clip,engine_factory=factory)
    assert result['status']=='counterfactuals_evaluated'
    assert len(result['probes'])==len(PROBES)
    assert result['changed_outcome_probes'] >= 1
    assert all(eng.closed for eng in made)
    with pytest.raises(ValueError,match='valid baseline'):
        compare_probe({'baseline_fidelity_pass':False}, {'attacker_scored':False})


def test_no_fidelity_when_wrong_score_or_too_early():
    clip=mkclip();c=candidate('goal.npz',clip.replay_sha)
    class WrongEngine(FakeEngine):
        def step(self,commands,shared):
            state=super().step(commands,shared)
            if state.goal_scored:state.ball.position[1]=-6000
            return state
    out=audit_candidate(c,clip,engine_factory=WrongEngine)
    assert out['status']=='baseline_not_reproduced'
    assert len(out['probes'])==1
