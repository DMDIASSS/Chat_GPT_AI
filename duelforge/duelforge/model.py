import torch
from torch import nn
class ActorCritic(nn.Module):
    def __init__(self,width:int=512):
        super().__init__()
        def head(out):
            layers=[];n=109
            for _ in range(3):layers.extend([nn.Linear(n,width),nn.LayerNorm(width),nn.ReLU()]);n=width
            return nn.Sequential(*layers,nn.Linear(n,out))
        self.actor=head(90);self.critic=head(1)
        # Small initial action logits keep the fresh actor exploratory.
        nn.init.orthogonal_(self.actor[-1].weight,gain=.01);nn.init.zeros_(self.actor[-1].bias)
        nn.init.zeros_(self.critic[-1].bias)
    def forward(self,x:torch.Tensor,legal:torch.Tensor):
        return self.actor(x).masked_fill(~legal,-1e9),self.critic(x).squeeze(-1)
