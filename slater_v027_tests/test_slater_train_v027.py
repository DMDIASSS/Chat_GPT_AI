import sys
from pathlib import Path
import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import slater_cycle9_train_v027 as v


def test_run_name_rejects_paths_and_metacharacters():
    for x in ('../checkpoint','x/y','..','a b','x\\y','x.json',''):
        with pytest.raises(ValueError): v.safe_run(x)
    assert v.safe_run('campaign_027_A') == 'campaign_027_A'


def test_resume_only_isolated(tmp_path):
    root=tmp_path
    safe=root/'data'/'isolated'
    safe.mkdir(parents=True)
    fname=safe/'old.pt'
    fname.write_bytes(b'test')
    assert v.validate_resume(str(fname), root)==fname.resolve()
    not_safe=root/'data'/'original.pt'
    not_safe.write_bytes(b'test')
    with pytest.raises(ValueError):v.validate_resume(str(not_safe),root)
    with pytest.raises(ValueError):v.validate_resume(str(fname.with_suffix('.json')),root)


def test_balanced_reset_alternates_side_and_frozen_opponent(monkeypatch):
    def fake_parent_reset(self,seed):
        self.state=type('State',(),{})()
        self.previous={}
        self.obs='blue'
        return self.obs
    def fake_read(state, previous, observer, side='blue-0'):
        return side
    monkeypatch.setattr(v.base.Native1v1,'reset',fake_parent_reset)
    monkeypatch.setattr(v.base,'read_obs',fake_read)
    e=v.SideBalanced1v1.__new__(v.SideBalanced1v1)
    e.opponents=('cycle9','nexto')
    e.episode_count=0
    e.observer=None
    results=[]
    for i in range(8):
        results.append((e.reset(i),e.opponent,e.current_opponent))
    assert results==[
        ('blue-0','cycle9','cycle9'),('orange-0','cycle9','cycle9'),
        ('blue-0','nexto','nexto'),('orange-0','nexto','nexto'),
        ('blue-0','cycle9','cycle9'),('orange-0','cycle9','cycle9'),
        ('blue-0','nexto','nexto'),('orange-0','nexto','nexto'),
    ]


def test_blue_orange_reward_signs(monkeypatch):
    class Physics:
        def __init__(self):self.position=np.array([0.,0.,17.],dtype=np.float32)
    class Car:
        def __init__(self):self.physics=Physics();self.ball_touches=1
    class Ball:
        def __init__(self):self.position=np.array([0.,0.,93.],dtype=np.float32)
    class State:
        def __init__(self):
            self.ball=Ball();self.cars={'blue-0':Car(),'orange-0':Car()};self.goal_scored=False
    class Engine:
        def __init__(self,s):self.s=s
        def step(self,commands,shared):
            assert set(commands)=={'orange-0','blue-0'}
            assert commands['blue-0'].shape==(8,8)
            self.s.ball.position[1]=-6000.
            self.s.goal_scored=True
            return self.s
    class Net(torch.nn.Module):
        def forward(self,x):return torch.zeros(1,90)
    monkeypatch.setattr(v.base,'read_obs',lambda *a,**k:(np.zeros((1,32)),np.zeros((41,24)),np.zeros(41)))
    e=v.SideBalanced1v1.__new__(v.SideBalanced1v1)
    e.actions=np.zeros((90,8),dtype=np.float32)
    e.student_side='orange';e.current_opponent='nexto';e.opponent=Net();e.device='cpu'
    e.state=State();e.engine=Engine(e.state);e.observer=None;e.previous={};e.t=0
    e.max_steps=10;e.touches=0;e.opponent_touches=0;e.total_reward=0
    _,reward,done,info=e.step(3)
    assert done and info['outcome']==1 and info['student_side']=='orange' and reward>9.
    assert info['student_touches']==1


def test_resume_checkpoint_format_and_optimizers(tmp_path):
    model=torch.nn.Linear(4,3)
    critic=torch.nn.Linear(4,1)
    ao=torch.optim.Adam(model.parameters(),lr=1e-4)
    co=torch.optim.Adam(critic.parameters(),lr=1e-4)
    p=tmp_path/'old.pt'
    torch.save({'stage':'slater_v027','source_sha':'okay','global_updates':20,
                'actor':model.state_dict(),'critic':critic.state_dict(),
                'actor_optimizer':ao.state_dict(),'critic_optimizer':co.state_dict()},p)
    assert v.resume_checkpoint(model,critic,ao,co,p,'okay')==20
    with pytest.raises(ValueError):v.resume_checkpoint(model,critic,ao,co,p,'wrong')
