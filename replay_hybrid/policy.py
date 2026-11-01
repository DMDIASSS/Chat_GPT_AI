"""Autoregressive PPO likelihoods and a separate return critic."""
import torch
from torch import nn
from torch.distributions import Categorical


class ReturnCritic(nn.Module):
    # This predicts shaped discounted returns, NOT the search head's next goal.
    def __init__(self):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(80,256),nn.Tanh(),nn.Linear(256,256),nn.Tanh(),nn.Linear(256,1))

    def forward(self,observations):
        q,kv,mask=observations
        legal=(mask==0).to(kv.dtype).unsqueeze(-1)
        mean=(kv*legal).sum(1)/legal.sum(1).clamp_min(1)
        return self.net(torch.cat((q[:,0],mean,kv[:,6]),-1))[:,0]


def fixed_decoder(model):
    """Keep each code tuple's controls fixed during PPO updates.

    The original offset depends on trainable state features. PPO ratios over
    codes would not account for changes to that deterministic offset. Disable
    it in this isolated child, then freeze codec/offset; preserve the parent.
    """
    with torch.no_grad():
        model.offset[-1].weight.zero_();model.offset[-1].bias.zero_()
    for name,parameter in model.named_parameters():
        parameter.requires_grad_(not name.startswith(('codec.','offset.')))
    return model


def statistics(model,observations,codes):
    if torch.is_inference(codes):codes=codes.clone()
    features=model.encode(observations);logits=model.teacher_logits(features,codes)
    distribution=Categorical(logits=logits)
    return distribution.log_prob(codes).sum(-1),distribution.entropy().sum(-1),features,logits


@torch.inference_mode()
def sample(model,observations):
    features=model.encode(observations);hidden=features;codes=[];logp=features.new_zeros(len(features))
    for level in range(model.codec.levels):
        if level:hidden=model.cell(model.embeddings[level-1](codes[-1]),hidden)
        distribution=Categorical(logits=model.heads[level](hidden));code=distribution.sample()
        codes.append(code);logp+=distribution.log_prob(code)
    codes=torch.stack(codes,-1)
    return model.actions(features,codes),codes,logp


def gae(rewards,values,next_values,terminated,truncated,gamma,lam=.95):
    """Time-limit bootstraps use the true final state; no cross-reset leakage."""
    advantage=torch.zeros_like(rewards);carry=torch.zeros_like(rewards[0])
    for i in range(len(rewards)-1,-1,-1):
        delta=rewards[i]+gamma*(~terminated[i]).to(values.dtype)*next_values[i]-values[i]
        carry=delta+gamma*lam*(~(terminated[i]|truncated[i])).to(values.dtype)*carry
        advantage[i]=carry
    return advantage,advantage+values


def clipped_loss(logp,old_logp,advantage,epsilon=.15):
    change=logp-old_logp;ratio=change.exp()
    loss=-torch.minimum(ratio*advantage,ratio.clamp(1-epsilon,1+epsilon)*advantage).mean()
    kl=(ratio-1-change).mean()
    return loss,kl
