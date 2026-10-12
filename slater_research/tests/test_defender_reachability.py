"""Pure Python tests of conservative reachability classification and isolated control probes."""
import copy
import numpy as np
import pytest
from types import SimpleNamespace as NS

from slater_research.defender_reachability import (
    POLICIES,policy_action,pursuit_action,baseline_accepted,compare_intervention,
    audit_one, audit)
from slater_research.tests.test_verified_defender_env import sample,FakeEngine


def make_state():
    return NS(ball=NS(position=np.array([0.,100.,250.]),
                      linear_velocity=np.array([200.,0.,0.])),
              cars={2:NS(physics=NS(position=np.array([0.,0.,17.]),
                                    rotation_mtx=np.eye(3)))})


def test_pursuit_is_finite_and_steers_both_directions():
    state=make_state()
    l=pursuit_action(state,2,turn_sign=-1)
    r=pursuit_action(state,2,turn_sign=1)
    assert l.shape==(8,) and np.all(np.abs(l)<=1)
    assert l[1]==-r[1] and l[1]!=0
    with pytest.raises(ValueError):pursuit_action(state,2,turn_sign=0)


def test_policy_actions_are_safe_and_jump_edge_triggered():
    state=make_state(); replay=np.array([.3,0,0,0,0,0,0,0],np.float32)
    for name in POLICIES:
        out=policy_action(name,state,2,step_index=0,replay_action=replay)
        assert out.shape==(8,) and np.isfinite(out).all() and np.max(np.abs(out))<=1
    assert policy_action('jump_boost',state,2,step_index=0,replay_action=replay)[5]==1
    assert policy_action('jump_boost',state,2,step_index=1,replay_action=replay)[5]==0
    assert np.array_equal(policy_action('replay',state,2,step_index=1,replay_action=replay),replay)
    with pytest.raises(ValueError):policy_action('unknown',state,2,step_index=0,replay_action=replay)


def test_timeout_is_never_a_confirmed_save():
    base=dict(attacker_scored=True,goal_offset_s=8/120,endpoint_ball_error_uu=4.,
              peak_reference_error_uu=20.,endpoint_ball_xyz=[1.,2.,3.])
    probe=dict(attacker_scored=False,defender_scored=False,defender_touch_observed=True,
               no_goal_by_deadline=True,endpoint_ball_xyz=[1.,4.,3.])
    assert baseline_accepted(base)
    result=compare_intervention(base,probe)
    assert result['changed_goal_outcome_by_deadline'] and result['touch_and_no_goal_by_deadline']
    assert result['endpoint_diversion_from_reference_uu']==2
    assert 'not_a_confirmed_save' in result['interpretation']
    base['peak_reference_error_uu']=251
    assert not baseline_accepted(base)
    base['peak_reference_error_uu']=20; base['goal_offset_s']=-0.1
    assert not baseline_accepted(base)


def test_audit_one_requires_faithful_positive_control_and_closes_engines():
    clip,meta=sample();made=[]
    def factory():
        engine=FakeEngine();made.append(engine);return engine
    # Physics fake supports reference and brake counterfactual. It has no car
    # physics vectors, so do not test dynamic pursuit on this fixture.
    rows=audit_one(clip,meta,factory,policies=('replay','brake','neutral'))
    assert rows['status']=='probes_complete'
    assert len(rows['runs'])==3
    assert rows['runs'][1]['no_goal_by_deadline']
    assert rows['runs'][1]['changed_goal_outcome_by_deadline']
    assert all(e.closed for e in made)


def test_run_on_empty_catalog_and_zero_selected(tmp_path):
    fake={'schema_version':1,'candidates':[]}
    result=audit(tmp_path,fake,limit=1,engine_factory=FakeEngine,progress=lambda *args,**kwargs:None)
    assert result['summary']['probe_trials']==0
    assert result['summary']['selected']==0
