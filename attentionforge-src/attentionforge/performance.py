"""Execution helpers. These preserve categorical sampling and PPO objectives."""
import torch
from torch.nn import functional as F

def sample_actions(logits):
    # Exponential-race categorical sampling: argmax(logits - log(Exp(1))).
    # Same distribution as softmax/multinomial, without validation reductions
    # that synchronize the GPU with the CPU on every decision.
    noise=torch.empty_like(logits).exponential_().clamp_min_(torch.finfo(logits.dtype).tiny).log_()
    action=(logits-noise).argmax(-1)
    log_prob=F.log_softmax(logits,dim=-1).gather(-1,action.unsqueeze(-1)).squeeze(-1)
    return action,log_prob

class RolloutStore:
    """Reuse rollout tensors across PPO epochs; bounded optional GPU cache."""
    def __init__(self,arrays,device,cache_mb=512):
        self.device=device;self.cached=False
        size=sum(a.nbytes for a in arrays)
        if device.type=='cuda' and cache_mb>0:
            free,_=torch.cuda.mem_get_info(device)
            self.cached=size<=min(cache_mb*1024**2,free*.35)
        if self.cached:
            # One transfer per buffer, not another full observation transfer every epoch.
            self.tensors=[torch.as_tensor(a,device=device) for a in arrays]
        else:self.tensors=[torch.from_numpy(a) for a in arrays]
    def permutation(self,indices):
        return torch.as_tensor(indices,device=self.device if self.cached else 'cpu')
    def get(self,index):
        return tuple(t.index_select(0,index).to(self.device) for t in self.tensors)
