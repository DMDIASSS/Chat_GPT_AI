"""Fresh spatial encoder and a small causal temporal chunk policy."""
import torch
from torch import nn

class SpatialBlock(nn.Module):
    def __init__(self):
        super().__init__();self.attention=nn.MultiheadAttention(128,4,batch_first=True)
        self.linear1=nn.Linear(128,512);self.linear2=nn.Linear(512,128)
        self.norm1=nn.LayerNorm(128);self.norm2=nn.LayerNorm(128);self.norm3=nn.LayerNorm(128)
    def forward(self,q,kv,mask):
        normalized=self.norm2(kv)
        q=q+self.attention(self.norm1(q),normalized,normalized,key_padding_mask=mask,need_weights=False)[0]
        return q+self.linear2(torch.relu(self.linear1(self.norm3(q))))

class Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.query_preprocess=nn.Sequential(nn.Linear(32,128),nn.ReLU(),nn.Linear(128,128),nn.ReLU())
        self.key_value_preprocess=nn.Sequential(nn.Linear(24,128),nn.ReLU(),nn.Linear(128,128),nn.ReLU())
        self.blocks=nn.ModuleList([SpatialBlock(),SpatialBlock()])
    def forward(self,obs):
        q,kv,mask=obs;q=self.query_preprocess(q);kv=self.key_value_preprocess(kv)
        for block in self.blocks:q=block(q,kv,mask)
        return q[:,0]

class ChunkPolicy(nn.Module):
    def __init__(self,vocabulary=256,history=8,width=256,layers=4,feedforward=768):
        super().__init__();self.encoder=Encoder();self.history=history
        self.project=nn.Linear(128,width);self.position=nn.Parameter(torch.zeros(1,history,width))
        block=nn.TransformerEncoderLayer(width,8,feedforward,dropout=0.,activation='gelu',batch_first=True,norm_first=True)
        self.temporal=nn.TransformerEncoder(block,layers,enable_nested_tensor=False)
        self.norm=nn.LayerNorm(width);self.policy=nn.Linear(width,vocabulary)
        self.values=nn.ModuleList([nn.Sequential(nn.Linear(width,128),nn.GELU(),nn.Linear(128,1)) for _ in range(3)])
        self.config=dict(vocabulary=vocabulary,history=history,width=width,layers=layers,feedforward=feedforward)
    def forward(self,observations):
        q,kv,mask=observations;b,n=q.shape[:2]
        history=self.encoder((q.reshape(b*n,1,32),kv.reshape(b*n,41,24),mask.reshape(b*n,41))).reshape(b,n,128)
        if n>self.history:raise ValueError('History exceeds model context')
        x=self.project(history)+self.position[:,:n]
        causal=torch.ones(n,n,dtype=torch.bool,device=x.device).triu(1)
        x=self.norm(self.temporal(x,mask=causal)[:,-1])
        return self.policy(x),torch.cat([head(x).tanh() for head in self.values],-1)
    def describe(self):
        return {'parameters':sum(p.numel() for p in self.parameters()),
                'trainable_parameters':sum(p.numel() for p in self.parameters() if p.requires_grad),**self.config}
