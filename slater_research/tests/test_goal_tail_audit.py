"""Read-only audit math / guardrails (does not need RocketSim installed)."""
import math
import numpy as np
import pytest
from slater_research.goal_tail_audit import GOAL_THRESHOLD_Y, reference_status, grade


def test_goal_threshold_strict_crossing():
    assert reference_status(5215.5)['reference_beyond_goal_trigger'] is False
    assert reference_status(5215.6)['reference_beyond_goal_trigger'] is True
    assert reference_status(-5215.4)['y_to_goal_trigger_uu'] == pytest.approx(.1)
    assert reference_status(5204)['y_to_goal_trigger_uu'] == pytest.approx(11.5)


def test_endpoint_good_but_not_yet_scored_has_separate_result():
    r=grade(endpoint_error=.036,peak_error=28.,max_error=250.,
            early_goal=False,goal_step=None,reference_goal_step=100,
            correct_goal=False,post_budget_steps=4)
    assert r['endpoint_position_matched']
    assert r['entire_reference_window_matched']
    assert not r['verified_goal_by_deadline']
    assert not r['accepted']
    assert r['reason']=='goal_not_verified_in_tail'


def test_goal_two_extra_decision_steps_later_passes():
    r=grade(endpoint_error=35,peak_error=42,max_error=250,
            early_goal=False,goal_step=102,reference_goal_step=100,
            correct_goal=True,post_budget_steps=4)
    assert r['accepted'] and r['verified_goal_by_deadline']


def test_score_too_late_or_wrong_team_does_not_pass():
    for goal_step,correct in [(105,True),(102,False)]:
        r=grade(endpoint_error=2,peak_error=25,max_error=250,
                early_goal=False,goal_step=goal_step,reference_goal_step=100,
                correct_goal=correct,post_budget_steps=4)
        assert not r['accepted']


def test_early_goal_rejected_even_with_low_stopped_error():
    r=grade(endpoint_error=None,peak_error=1,max_error=250,
            early_goal=True,goal_step=99,reference_goal_step=100,
            correct_goal=True,post_budget_steps=4)
    assert not r['accepted']
    assert r['reason']=='early_goal_unverifiable'


def test_max_flight_error_matters_even_if_endpoint_matches():
    r=grade(endpoint_error=3,peak_error=520,max_error=250,
            early_goal=False,goal_step=102,reference_goal_step=100,
            correct_goal=True,post_budget_steps=4)
    assert r['endpoint_position_matched']
    assert not r['entire_reference_window_matched']
    assert not r['accepted']


def test_bad_nonfinite_input():
    with pytest.raises(ValueError): reference_status(math.nan)
    for bad in (math.inf,math.nan):
        r=grade(endpoint_error=bad,peak_error=bad,max_error=250,
                early_goal=False,goal_step=100,reference_goal_step=100,
                correct_goal=True,post_budget_steps=0)
        assert not r['accepted']


def test_actual_sim_tail_path_with_mocked_engine(monkeypatch):
    """A subthreshold reference endpoint must get more RocketSim steps."""
    import sys
    import copy
    from types import ModuleType, SimpleNamespace
    from slater_research.goal_tail_audit import audit_window
    from slater_research.replay_engine import Clip

    def snap(y):
        return SimpleNamespace(
            ball=SimpleNamespace(position=np.array([0.,y,100.],dtype=np.float32)),
            cars={1:SimpleNamespace(is_orange=False),
                  2:SimpleNamespace(is_orange=True)},
            goal_scored=False)

    class FakeEngine:
        def __init__(self,**kwargs):
            self.state=None
        def set_state(self, s, shared):
            self.state=copy.deepcopy(s)
            return self.state
        def step(self,actions,shared):
            self.state.ball.position[1] += 80.
            self.state.goal_scored=bool(self.state.ball.position[1]>5215.5)
            return self.state
        def close(self): pass

    # Never import a networked or installed RocketSim in a unit test.
    for name in ['rlgym','rlgym.rocket_league','rlgym.rocket_league.sim']:
        fake=ModuleType(name);fake.__path__=[]
        monkeypatch.setitem(sys.modules,name,fake)
    sys.modules['rlgym.rocket_league.sim'].RocketSimEngine=FakeEngine

    clip=Clip(snapshots=[snap(5100.),snap(5180.)],
              controls=np.zeros((2,2,8),dtype=np.float32),
              ids=(1,2), shooter_id=1, goal_step=1, replay_sha='0'*64)
    out=audit_window(clip,.25,'all_dynamic',post_seconds=.3,max_error=250)
    assert out['reference_beyond_goal_trigger'] is False
    assert out['endpoint_position_matched']
    assert out['entire_reference_window_matched']
    assert out['scored_in_post_rollout']
    assert out['actual_goal_step']==2
    assert out['goal_offset_s']==pytest.approx(8/120)
    assert out['accepted']

    # With no tail, this is still a valid position match, but not a goal pass.
    out0=audit_window(clip,.25,'all_dynamic',post_seconds=0,max_error=250)
    assert out0['endpoint_position_matched']
    assert not out0['accepted']
