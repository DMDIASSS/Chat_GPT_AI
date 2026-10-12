import sys
from pathlib import Path
import numpy as np
import pytest
import torch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import slater_fullmatch_eval_v030 as fm
import slater_export_rlbot_v030 as ex

class FakeEnv:
    device='cpu'
    def __init__(self, outcome_by_kickoff, steps_per_goal=3):
        self.outcomes=outcome_by_kickoff
        self.steps_per_goal=steps_per_goal
        self.reset_count=0
        self.t=0
        self.max_steps=0
        self.info={}
        self.state=self
    def reset(self,seed):
        self.last_seed=seed
        self.t=0
        self.reset_count+=1
        return object()
    def step(self,act):
        self.t+=1
        outcome=self.outcomes[min(self.reset_count-1,len(self.outcomes)-1)] if self.t==self.steps_per_goal else 0
        # reset as soon as goal or at provided time
        done=bool(outcome or self.t>=self.max_steps)
        return object(),0.0,done,{
            'outcome':outcome,'student_touches':self.t,'opponent_touches':self.t//2,
            'timeout':bool(done and not outcome), 'steps':self.t,
        }

def test_clock_regulation_multiple_goals(monkeypatch):
    monkeypatch.setattr(fm,'seeded_reset',lambda env,seed:(env.reset(seed),'same-kickoff'))
    monkeypatch.setattr(fm.paired,'greedy_action',lambda *a,**k:0)
    env=FakeEnv([1,-1,1],steps_per_goal=3)
    row=fm.one_full_match(env,object(),9,'blue',11,0)
    assert row['goals_for']==2 and row['goals_against']==1
    assert row['decisions']==11 and row['kickoffs']==4
    assert row['goal_events'][2]['step']==9
    assert row['outcome']==1

def test_overtime_sudden_death(monkeypatch):
    monkeypatch.setattr(fm,'seeded_reset',lambda env,seed:(env.reset(seed),'same'))
    monkeypatch.setattr(fm.paired,'greedy_action',lambda *a,**k:0)
    env=FakeEnv([0,1],steps_per_goal=3)
    row=fm.one_full_match(env,object(),3,'orange',4,7)
    assert row['overtime'] and row['decisions']==4+7 and row['draw']
    env=FakeEnv([1,-1,1],steps_per_goal=3)
    row=fm.one_full_match(env,object(),3,'blue',6,7)
    assert row['overtime'] and row['decisions']==9 and row['outcome']==1

def test_paired_aggregation():
    rows=[]
    for seed in (1,2,3):
        for side in ('blue','orange'):
            for policy,outcome in (('original',-1),('u60',1)):
                rows.append({'seed':seed,'side':side,'policy':policy,'outcome':outcome,
                             'goal_diff':outcome,'goals_for':int(outcome==1),
                             'goals_against':int(outcome==-1),'touches':10,
                             'opponent_touches':4,'overtime':False})
    b=fm.aggregate([r for r in rows if r['policy']=='u60'])
    assert b['win_rate']==1.0 and b['matches']==6 and b['draws']==0
    c=fm.compare_by_seed(rows,'u60')
    assert c['win_rate']['delta']==1.0
    assert c['goal_diff']['delta']==2.0

def test_export_roundtrip_is_create_only(tmp_path,monkeypatch):
    root=tmp_path
    isolated=root/'data'/'isolated';isolated.mkdir(parents=True)
    vendor=root/'vendor.pt'
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__();self.weight=torch.nn.Parameter(torch.tensor([[1.,2.]]))
        def forward(self,x):return x @ self.weight.T
    torch.jit.trace(Net(),torch.ones((1,2))).save(str(vendor))
    sha=ex.base.sha256(vendor)
    source_model=torch.jit.load(str(vendor),map_location='cpu')
    expected={k:torch.full_like(v,3.) for k,v in source_model.state_dict().items()}
    cp=isolated/'test.pt'
    torch.save({'stage':'slater_v027','source_sha':'A',
                'global_updates':60,'actor':expected,'meta':{'nexto_sha':sha}},cp)
    dest=isolated/'export.pt'
    info=ex.export_model(cp,vendor,dest,'A',sha,root)
    assert info['global_updates']==60
    out=torch.jit.load(str(dest))
    assert all(torch.equal(v,expected[k]) for k,v in out.state_dict().items())
    with pytest.raises(FileExistsError):ex.export_model(cp,vendor,dest,'A',sha,root)
    assert dest.is_file() # existing export NOT deleted on a preexist failure


def test_mismatched_sources_rejected(tmp_path):
    root=tmp_path; iso=root/'data'/'isolated';iso.mkdir(parents=True)
    cp=iso/'fake.pt'
    torch.save({'stage':'slater_v027','source_sha':'A','actor':{'a':torch.tensor(1.)},
                'global_updates':60,'meta':{'nexto_sha':'N'}},cp)
    with pytest.raises(FileNotFoundError):
        ex.export_model(cp,root/'bad.pt',iso/'new.pt','A','N',root)
    assert not (iso/'new.pt').exists()
