import torch
import numpy as np
from slater_research.action_precision import KickoffPrecisionHead,ticks_per_decision,compose_controls

def test_residual_safe_initialization():
    h=KickoffPrecisionHead()
    q=torch.randn(3,1,32);kv=torch.randn(3,41,24);mask=torch.zeros(3,41)
    out=h(q,kv,mask,torch.zeros(3))
    assert torch.all(out==0)
    assert ticks_per_decision(True,0.8)==2
    assert ticks_per_decision(False,0.8)==8
    a=np.array([1,0,0,0,0,1,1,0])
    result=compose_controls(a,np.ones(8))
    assert result[5]==1 and result[6]==1
