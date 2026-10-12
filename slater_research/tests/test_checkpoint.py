import torch
from slater_research.checkpoint import stable_kl,guarded_ppo_loss

def test_identical_anchor():
    logits=torch.tensor([[0.1,0.7,1.1]])
    assert abs(float(stable_kl(logits,logits)))<1e-6

def test_ppo_gradient():
    x=torch.randn(8,5,requires_grad=True)
    y=torch.zeros_like(x)
    actions=torch.arange(8)%5
    old=torch.log_softmax(x.detach(),dim=-1).gather(1,actions[:,None]).squeeze(1)
    loss=guarded_ppo_loss(x,y,actions,old,torch.ones(8))
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(x.grad).all()


def test_cycle9_pair_loads_teacher_independently(tmp_path,monkeypatch):
    import hashlib
    from pathlib import Path
    import torch
    import slater_research.checkpoint as m
    sample=torch.nn.Linear(2,3)
    cp=tmp_path/'cycle9.pt'
    torch.save({'actor':sample.state_dict()},cp)
    monkeypatch.setattr(m,'CYCLE9',Path('cycle9.pt'))
    monkeypatch.setattr(m,'CYCLE9_SHA',hashlib.sha256(cp.read_bytes()).hexdigest())
    monkeypatch.setattr(torch.jit,'load',lambda *_args,**_kwargs: torch.nn.Linear(2,3))
    actor,teacher=m.cycle9_pair(tmp_path)
    a,b=list(actor.parameters())[0],list(teacher.parameters())[0]
    assert a.data_ptr()!=b.data_ptr()
    assert torch.equal(a,b)
    with torch.no_grad():a.add_(0.2)
    assert not torch.equal(a,b)
