import sys
from pathlib import Path
import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import slater_nexto_heldout_eval_v028 as e


def test_identical_game_detection():
    x = {'seed':9,'side':'blue','kickoff_signature':'abc','outcome':1,
         'touches':2,'opponent_touches':4,'steps':3,'final_ball_progress_uu':55.}
    assert e.check_same_game(x, dict(x))
    for field in ('outcome','steps','kickoff_signature','touches'):
        y = dict(x)
        y[field] = 'different'
        assert not e.check_same_game(x, y)


def test_kickoff_fingerprint_tracks_changes():
    class P:
        def __init__(self, y):
            self.position=np.array([0.,y,17.])
            self.linear_velocity=np.zeros(3)
            self.angular_velocity=np.zeros(3)
            self.forward=np.array([1.,0.,0.])
    class Car:
        def __init__(self, y): self.physics=P(y); self.boost_amount=33
    class State:
        def __init__(self, y): self.ball=P(0.);self.cars={'blue-0':Car(y),'orange-0':Car(-y)}
    class Env:
        def __init__(self, y): self.state=State(y)
    assert e.kickoff_signature(Env(10)) == e.kickoff_signature(Env(10))
    assert e.kickoff_signature(Env(10)) != e.kickoff_signature(Env(11))


def test_reject_candidate_outside_isolated(tmp_path):
    root=tmp_path
    not_iso=root/'out.pt'
    not_iso.write_bytes(b'spoof')
    with pytest.raises(ValueError):e.checked_candidate(str(not_iso), root, 'source', 'nexto')
    with pytest.raises(ValueError):e.checked_candidate(str(root/'data/isolated/missing.pt'),root,'source','nexto')


def test_candidate_metadata_must_match(tmp_path):
    root=tmp_path
    iso=root/'data/isolated';iso.mkdir(parents=True)
    cp=iso/'cp.pt'
    torch.save({'stage':'slater_v027','source_sha':'A','actor':{'a':torch.ones(3)},
                'global_updates':60,'meta':{'nexto_sha':'N'}}, cp)
    p,doc=e.checked_candidate(str(cp),root,'A','N')
    assert p==cp.resolve() and doc['global_updates']==60
    with pytest.raises(ValueError):e.checked_candidate(str(cp),root,'B','N')
    with pytest.raises(ValueError):e.checked_candidate(str(cp),root,'A','wrong')


def test_reseed_numpy_and_python_for_each_run(monkeypatch):
    import random
    class Env:
        device='cpu'
        def reset(self,seed):
            self.x=float(np.random.rand())
            self.y=float(random.random())
            self.state=object()
            return object()
        def step(self,action):
            return None,0.,True,{'outcome':0,'student_touches':3,'opponent_touches':1,
                                 'steps':1,'ball_y':self.x+self.y}
    monkeypatch.setattr(e,'kickoff_signature',lambda env:f'{env.x:.9f} {env.y:.9f}')
    monkeypatch.setattr(e.paired,'greedy_action',lambda *args,**kwargs:1)
    a=e.deterministic_game(Env(),object(),2181,'blue')
    b=e.deterministic_game(Env(),object(),2181,'blue')
    assert e.check_same_game(a,b)
    assert not e.check_same_game(a,e.deterministic_game(Env(),object(),2182,'blue'))
