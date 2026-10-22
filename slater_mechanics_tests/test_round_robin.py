import numpy as np
import pytest
import torch

import round_robin_evaluator as rr


class Actor(torch.nn.Module):
    def __init__(self):super().__init__();self.layer=torch.nn.Linear(32,90)
    def forward(self,x):return self.layer(x)


def test_discovery_reads_torchscript_and_deduplicates_actor_not_optimizer(tmp_path,monkeypatch):
    vendor=tmp_path/'vendor/nexto';vendor.mkdir(parents=True)
    model=torch.jit.trace(Actor(),torch.zeros(1,32))
    model.save(str(vendor/'nexto-model.pt'))
    a=tmp_path/'a.pt';b=tmp_path/'b.pt'
    torch.save({'actor':model.state_dict(),'global_updates':1},a)
    torch.save({'actor':model.state_dict(),'global_updates':99,'actor_optimizer':{'x':2}},b)
    changed={k:v.clone() for k,v in model.state_dict().items()}
    changed['layer.bias'][0]+=.01
    torch.save({'actor':changed},tmp_path/'c.pt')
    bad={k:v.clone() for k,v in changed.items()};bad['layer.bias'][0]=float('nan')
    torch.save({'actor':bad},tmp_path/'d.pt')
    monkeypatch.setattr(rr,'ROOT',tmp_path)
    bots,inv=rr.discover({},256,all_scripted=True)
    assert len(bots)==2
    assert sum(v['kind']=='DUPLICATE' for v in inv)==2
    assert next(v for v in inv if v['path']=='d.pt')['kind']=='UNSUPPORTED'
    assert all(b['kickoff']=='nexto_v4' for b in bots)
    # With per-model rules, equal neural actors with different kickoff behavior
    # are distinct configurations, including the public TorchScript baseline.
    bots,inv=rr.discover({},256)
    assert any(b['kind']=='NEXTO_TS' for b in bots)
    assert len(bots)==3
    bots,inv=rr.discover({},256,all_scripted=True,include=['c.pt'])
    assert len(bots)==1 and bots[0]['path']=='c.pt'
    assert sum(v['kind']=='FILTERED' for v in inv)==4


def test_every_pair_has_same_seeds_and_both_sides():
    rows=list(rr.schedule([{}, {}, {}],50,9))
    assert len(rows)==150
    for pair in ((0,1),(0,2),(1,2)):
        games=[r for r in rows if r[:2]==pair]
        assert len(games)==50
        assert all(games[i][2]==games[i+1][2] and games[i][3]!=games[i+1][3]
                   for i in range(0,50,2))


def test_equal_weights_have_same_identity_even_in_different_container():
    a={'x':torch.tensor([1.,2.]),'scalar':torch.tensor(1.)}
    b={k:v.clone() for k,v in reversed(list(a.items()))}
    assert rr.weight_digest(a)==rr.weight_digest(b)
    b['x'][0]+=1
    assert rr.weight_digest(a)!=rr.weight_digest(b)


def test_standings_keep_timeout_counts_visible():
    bots=[{'id':n,'path':n,'sha':'s','kind':'NATIVE','kickoff':'nexto_v4'} for n in ('a','b')]
    board,head=rr.standings(bots,[{'a':'a','b':'b','outcome':'W1'},
                                {'a':'a','b':'b','outcome':'D'}])
    assert board[0]['model']=='a' and board[0]['score_pct']==75
    assert board[0]['D']==1 and head[0]['games']==2
