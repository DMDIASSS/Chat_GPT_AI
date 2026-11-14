import torch
from torch import nn

class QueryBlock(nn.Module):
    def __init__(self, width, heads):
        super().__init__()
        self.qnorm=nn.LayerNorm(width); self.knorm=nn.LayerNorm(width)
        self.attention=nn.MultiheadAttention(width,heads,dropout=0.0,batch_first=True)
        self.norm=nn.LayerNorm(width)
        self.ff=nn.Sequential(nn.Linear(width,width*2),nn.GELU(),nn.Linear(width*2,width))
    def forward(self,q,entities,padding):
        k=self.knorm(entities)
        q=q+self.attention(self.qnorm(q),k,k,key_padding_mask=padding,need_weights=False)[0]
        return q+self.ff(self.norm(q))

class ActorCritic(nn.Module):
    def __init__(self,width=64,heads=4,blocks=2):
        super().__init__()
        self.numeric=nn.Linear(39,width); self.types=nn.Embedding(7,width,padding_idx=0)
        self.blocks=nn.ModuleList([QueryBlock(width,heads) for _ in range(blocks)])
        self.norm=nn.LayerNorm(width); self.actor=nn.Linear(width,90);self.critic=nn.Linear(width,1)
        nn.init.orthogonal_(self.actor.weight,0.01);nn.init.zeros_(self.actor.bias)
        nn.init.orthogonal_(self.critic.weight,1);nn.init.zeros_(self.critic.bias)
    def forward(self,tokens,legal):
        types=tokens[:,:,39].long(); entities=self.numeric(tokens[:,:,:39])+self.types(types)
        q=entities[:,:1]; padding=types==0
        for block in self.blocks:q=block(q,entities,padding)
        x=self.norm(q[:,0]);logits=self.actor(x).masked_fill(~legal,-1e9)
        return logits,self.critic(x).squeeze(-1)
