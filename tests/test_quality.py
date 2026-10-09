import sys
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(Path('/mnt/data/Chat_GPT_AI_Fast_Track')), str(Path('/mnt/data/Chat_GPT_AI_Native_Nexto_Upgrade'))]
from native_quality_eval import evaluate_touch, is_controlled_ball, score_summaries, GameMetrics


def st(touches=0, bvy=0., ypos=0., ballz=90., cary=0., carvy=0.):
    def car(touch):
        return NS(ball_touches=touch, physics=NS(position=np.array([0., cary, 17.]), linear_velocity=np.array([0., carvy, 0.])))
    return NS(cars={0:car(touches),1:car(0)}, ball=NS(position=np.array([0.,ypos,ballz]), linear_velocity=np.array([0.,bvy,0.])))


def test_touch_velocity_progress():
    assert evaluate_touch(st(bvy=0), st(touches=1,bvy=700),0,False) == (True,False)
    assert evaluate_touch(st(bvy=0), st(touches=1,bvy=-700),0,False) == (False,True)
    assert evaluate_touch(st(bvy=0), st(touches=0,bvy=700),0,False) == (False,False)
    assert evaluate_touch(st(bvy=0), st(touches=1,bvy=-700),0,True) == (True,False)


def test_control_requires_last_touch_and_relative_speed():
    assert is_controlled_ball(st(touches=1),0,0)
    assert not is_controlled_ball(st(touches=1),0,1)
    assert not is_controlled_ball(st(touches=1,cary=2000),0,0)
    assert not is_controlled_ball(st(touches=1,carvy=2000),0,0)


def test_aggregate_normalizes_to_decision_ticks():
    g=GameMetrics(0,1,False)
    g.record(st(), st(touches=1,bvy=700,ypos=100), 16, 16)
    a=score_summaries([g.summary()])
    assert a['raw']['touches']['ours']==1
    assert a['raw']['productive_touches']['ours']==1
    assert a['rates']['ours']['touches_per_1000_ticks']==1000
    assert a['rates']['ours']['offensive_half_time_pct']==100
