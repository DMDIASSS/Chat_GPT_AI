import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('slater_nexto_scheduler_v038b',ROOT/'slater_nexto_scheduler_v038b.py')
import sys
sch=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=sch
SPEC.loader.exec_module(sch)


def positions():return (np.array([[0,-4608],[0,4608]],dtype=float),np.array([0,1]))

def fake_infer(previous,beta):return 16,np.array([1,0,0,0,0,0,1,0],dtype=np.float32)

def call(c, y=0, pause=True, positions_override=None, index=1, infer=fake_infer):
    pos,teams=positions() if positions_override is None else positions_override
    return c.frame(is_kickoff_pause=pause,ball_xy=(0,y),positions=pos,teams=teams,index=index,infer=infer)


def test_script_exact_hash_and_boundaries():
    assert sch.KICKOFF.shape==(168,8)
    assert np.all(sch.KICKOFF[:44,1]==0)
    assert np.all(sch.KICKOFF[44:60,1]==-1)
    assert np.all(sch.KICKOFF[60:68,5]==1)
    assert np.all(sch.KICKOFF[72:76,2]==-.7)
    assert np.all(sch.KICKOFF[128:,4]==1)


def test_clock_script_duration_and_action_values():
    c=sch.NextoV4Clock()
    for t in range(175):
        out=call(c)
        if t<168:
            assert out.script_applied
            assert out.kickoff_index==t
            np.testing.assert_array_equal(out.controls,sch.KICKOFF[t])
        else: assert not out.script_applied
    assert c.script_physics_ticks==168


def test_midstep_stop_without_reverting_to_old_input():
    c=sch.NextoV4Clock()
    for t in range(19):
        out=call(c,y=0 if t<4 else 200)
        if t<4: assert out.script_applied
        else:
            assert not out.script_applied
            assert out.script_interrupted
    assert c.script_physics_ticks==4
    assert c.interrupted_physics_ticks==15
    assert c.kickoff_index==18


def test_pause_reset_rearms_kickoff():
    c=sch.NextoV4Clock()
    for _ in range(5):call(c)
    out=call(c,pause=False)
    assert out.kickoff_index==-1
    assert not out.script_applied
    next_out=call(c,pause=True)
    assert next_out.kickoff_index==0
    assert next_out.script_applied


def test_taker_detection_1v1_and_multicar():
    p,t=positions()
    assert sch.NextoV4Clock.kickoff_taker(p,t,0,[0,0])
    assert sch.NextoV4Clock.kickoff_taker(p,t,1,[0,0])
    p=np.array([[0,-4608],[0,5000]])
    assert not sch.NextoV4Clock.kickoff_taker(p,np.array([0,1]),1,[0,0])
    # Explicitly match archived v4 code, including the counterintuitive
    # `if not is_left:` branch rather than silently 'fixing' its comment.
    p=np.array([[-500,-2000],[500,-2000],[0,4000]],dtype=float)
    t=np.array([0,0,1])
    assert sch.NextoV4Clock.kickoff_taker(p,t,0,[0,0]) is False
    assert sch.NextoV4Clock.kickoff_taker(p,t,1,[0,0]) is True


def test_non_taker_latched_until_new_kickoff():
    c=sch.NextoV4Clock()
    p=np.array([[0,-4608],[0,5120]],dtype=float)
    for _ in range(20):
        x=call(c,positions_override=(p,np.array([0,1])))
        assert x.kickoff_index==-2 and not x.script_applied
    call(c,pause=False)
    assert c.kickoff_index==-1


def test_prev_action_is_script_override_on_next_nn_decision():
    c=sch.NextoV4Clock()
    seen=[]
    def infer(prev,beta):
        seen.append((prev.copy(),beta))
        return 7,np.array([-.25,.5,-.5,.1,-.2,0,0,1],dtype=np.float32)
    for t in range(10):call(c,infer=infer)
    # Source v4: an inference at first tick then at next tick because ticks
    # starts at 8, and another after the next eight tick cycle.
    assert len(seen)>=2
    np.testing.assert_array_equal(seen[0][0],np.zeros(8))
    np.testing.assert_array_equal(seen[1][0],sch.KICKOFF[0])
    assert all(beta==.5 for _,beta in seen)


def test_hardcoded_vs_neural_switch():
    c=sch.NextoV4Clock(hardcoded=False,stochastic=False)
    for _ in range(12):
        x=call(c)
        assert not x.script_applied and not x.script_interrupted
    assert c.script_physics_ticks==0
    assert c.stochastic_nn_inferences==0
    assert c.nn_inferences>0


def test_stock_stochastic_does_not_replace_script():
    c=sch.NextoV4Clock(hardcoded=True,stochastic=True)
    for _ in range(50):
        x=call(c)
        assert x.script_applied
    assert c.stochastic_nn_inferences>0
    assert c.script_physics_ticks==50
    assert c.nn_inferences==c.stochastic_nn_inferences


def test_invalid_inputs():
    c=sch.NextoV4Clock()
    with pytest.raises(ValueError):call(c,index=2)
    with pytest.raises(ValueError):c.frame(is_kickoff_pause=True,ball_xy=[0,0],positions=np.array([[1,2]]),teams=np.array([1]),index=0,infer=fake_infer,ticks_elapsed=-1)


def test_script_float32_and_immutable_reference():
    assert sch.KICKOFF.dtype==np.float32
    first=sch.KICKOFF[0].copy()
    c=sch.NextoV4Clock()
    x=call(c)
    x.controls[0]=-1
    x.action[0]=-1
    np.testing.assert_array_equal(first,sch.KICKOFF[0])


def test_scheduler_matches_independent_reference_oracle():
    # A second independently written implementation of the legacy RLBot
    # state update order; compares generated controller output for changes of
    # pause and ball state. This is a code-level oracle, not live packet trace.
    clock=sch.NextoV4Clock()
    ticks=8;update=True;idx=-1;action=np.zeros(8,dtype=np.float32);controls=np.zeros(8,dtype=np.float32)
    for t in range(220):
        pause=t<195
        y=0 if t<36 else 180
        if t>=110:y=0
        # v4 get_output simplified: 120Hz packet, always the only taker.
        ticks+=1
        if update:
            update=False
            action=fake_infer(action,.5 if pause else 1.)[1].copy()
        if ticks>=7:controls=action.copy()
        if ticks>=8:ticks=0;update=True
        if pause:
            if idx>=0:idx+=1
            elif idx==-1:idx=0
            if 0<=idx<168 and y==0:
                action=sch.KICKOFF[idx].copy()
                controls=action.copy()
        else:idx=-1
        out=call(clock,y=y,pause=pause)
        assert out.kickoff_index==idx
        np.testing.assert_array_equal(out.action,action)
        np.testing.assert_array_equal(out.controls,controls)
