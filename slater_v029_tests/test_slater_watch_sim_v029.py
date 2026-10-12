import sys
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slater_watch_sim_v029 as m


def state(goal=False):
    def car(x,y):
        phy=N(position=np.array([x,y,17.]),linear_velocity=np.array([0.,100.,0.]),forward=np.array([0.,1.,0.]))
        return N(physics=phy,boost_amount=62.,ball_touches=0,on_ground=True)
    return N(goal_scored=goal,ball=N(position=np.array([0.,0.,93.]),linear_velocity=np.array([0.,0.,0.])),cars={'blue-0':car(-500,-3000),'orange-0':car(500,3000)})


def test_capture_coordinates_and_units():
    s=state()
    shot=m.capture(s,0,'blue')
    assert shot['ball']['p']==[0,0,93]
    assert shot['cars']['blue-0']['p']==[-500,-3000,17]
    assert shot['cars']['orange-0']['f']==[0,1,0]
    assert shot['cars']['blue-0']['touch']==0
    assert shot['goal'] is False
    shot=m.capture(s,2,'blue',{'blue-0':np.array([1,0,0,0,0,0,0,0.])})
    assert shot['cars']['blue-0']['action']==[1,0,0,0,0,0,0,0]


def test_outcome_signs():
    fr={'goal':True,'ball':{'p':[0,5121,93]}}
    assert m.outcome_from_frame(fr,'blue')==1
    assert m.outcome_from_frame(fr,'orange')==-1
    fr['ball']['p'][1]=-5121
    assert m.outcome_from_frame(fr,'orange')==1
    fr['goal']=False
    assert m.outcome_from_frame(fr,'blue')==0


def test_nonfinite_coordinates_rejected():
    s=state();s.ball.position[0]=float('nan')
    with pytest.raises(FloatingPointError):m.capture(s,0,'blue')


def test_output_isolated_create_only(tmp_path):
    root=tmp_path
    ok=root/'data'/'isolated'/'one.html'
    assert m.checked_output(ok,root)==ok.resolve()
    with pytest.raises(ValueError):m.checked_output(root/'data'/'other.html',root)
    with pytest.raises(ValueError):m.checked_output(root/'data'/'isolated'/'one.pt',root)
    ok.parent.mkdir(parents=True);ok.write_text('x')
    with pytest.raises(FileExistsError):m.checked_output(ok,root)


def test_html_offline_playback_and_no_external_dependencies():
    frame=m.capture(state(),0,'blue')
    doc=m.make_html([dict(frames=[frame],policy='original Cycle 9',side='blue',seed=17,timeout=True,outcome=0,student_touches=0,nexto_touches=0)])
    assert '<canvas' not in doc  # canvas is made with JS, not hardcoded
    assert 'GAMES = [' in doc
    assert 'original Cycle 9' in doc
    assert 'requestAnimationFrame' in doc
    assert 'https://' not in doc
    assert '__DATA__' not in doc
    assert '5120' in doc


def test_record_game_steps_existing_env(monkeypatch):
    class Fake:
        def __init__(self,actions,observer,nexto,max_steps,device):
            self.max_steps=max_steps;self.device=device;self.previous={};self.state=state()
        def reset(self,seed):
            self.state=state();return ('obs',)
        def step(self,a):
            self.state.ball.position[1]+=3000
            goal=self.state.ball.position[1]>5000
            self.state.goal_scored=goal
            self.previous={'blue-0':np.ones(8)*a, 'orange-0':np.zeros(8)}
            info=dict(outcome=1 if goal else 0,steps=int(self.state.ball.position[1]/3000),student_touches=1,opponent_touches=0,timeout=False,ball_y=float(self.state.ball.position[1]))
            return ('obs',),0.0,goal,info
        def close(self):pass
    monkeypatch.setattr(m.base,'Native1v1',Fake)
    monkeypatch.setattr(m.paired,'greedy_action',lambda *args:4)
    out=m.record_game(None,None,None,None,1,'blue',4)
    assert out['outcome']==1
    assert len(out['frames'])==3
    assert out['frames'][1]['cars']['blue-0']['action']==[4]*8
    assert out['frames'][2]['goal'] is True


def test_render_called_with_actual_state(monkeypatch):
    class Fake:
        def __init__(self,*args,**kwargs):self.state=state();self.device='cpu';self.previous={}
        def reset(self,seed):return ('obs',)
        def step(self,act):return ('obs',),0,True,{'outcome':0,'student_touches':0,'opponent_touches':0,'steps':1,'ball_y':0.,'timeout':True}
        def close(self):pass
    class Viewer:
        def __init__(self):self.seen=[]
        def render(self,st,info):self.seen.append(st)
    monkeypatch.setattr(m.paired,'RoleSwap1v1',Fake)
    monkeypatch.setattr(m.paired,'greedy_action',lambda *args:1)
    v=Viewer()
    r=m.record_game(None,None,None,None,1,'orange',5,v,4.0)
    assert len(v.seen)==2
    assert r['side']=='orange'
