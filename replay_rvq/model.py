"""Learned residual action codes and a current-state autoregressive policy."""
import math
import torch
from torch import nn
from torch.nn import functional as F
from replay_il.model import Encoder


class ActionCodec(nn.Module):
    def __init__(self,latent=128,hidden=512,levels=4,codes=64):
        super().__init__()
        self.latent=latent;self.levels=levels;self.codes=codes
        self.encoder=nn.Sequential(nn.Flatten(),nn.Linear(256,hidden),nn.GELU(),
            nn.Linear(hidden,latent),nn.LayerNorm(latent,elementwise_affine=False))
        self.codebooks=nn.Parameter(torch.randn(levels,codes,latent)/math.sqrt(levels))
        self.decoder=nn.Sequential(nn.Linear(latent,hidden),nn.GELU(),nn.Linear(hidden,256))
        self.register_buffer('button_thresholds',torch.zeros(3))
        self.config={'latent':latent,'hidden':hidden,'levels':levels,'codes':codes}

    def quantize(self,z):
        residual=z;total=torch.zeros_like(z);labels=[];loss=z.new_zeros(())
        for level in range(self.levels):
            book=self.codebooks[level]
            distance=(residual*residual).sum(-1,keepdim=True)+(book*book).sum(-1)-2*residual@book.T
            ids=distance.argmin(-1);q=F.embedding(ids,book);labels.append(ids)
            loss=loss+F.mse_loss(q,residual.detach())+.25*F.mse_loss(residual,q.detach())
            total=total+q;residual=residual-q.detach()
        return z+(total-z).detach(),torch.stack(labels,-1),loss/self.levels

    def latent_from_codes(self,codes):
        z=F.embedding(codes[...,0],self.codebooks[0])
        for level in range(1,self.levels):z=z+F.embedding(codes[...,level],self.codebooks[level])
        return z

    def decode_latent(self,z):return self.decoder(z).reshape(*z.shape[:-1],32,8)
    def decode_codes(self,codes):return self.decode_latent(self.latent_from_codes(codes))

    def forward(self,controls):
        z=self.encoder(controls);quantized,codes,vq=self.quantize(z)
        return self.decode_latent(quantized),codes,vq

    @torch.no_grad()
    def initialize(self,controls):
        """Train-only residual k-means seeding; subsequent codebooks are learned."""
        residual=self.encoder(controls).detach()
        for level in range(self.levels):
            ids=torch.randperm(len(residual),device=residual.device)
            centroids=residual[ids[torch.arange(self.codes,device=residual.device)%len(ids)]].clone()
            for _ in range(4):
                distance=(residual*residual).sum(-1,keepdim=True)+(centroids*centroids).sum(-1)-2*residual@centroids.T
                nearest=distance.argmin(-1)
                for code in range(self.codes):
                    selected=residual[nearest==code]
                    if len(selected):centroids[code]=selected.mean(0)
            self.codebooks[level].copy_(centroids)
            distance=(residual*residual).sum(-1,keepdim=True)+(centroids*centroids).sum(-1)-2*residual@centroids.T
            residual=residual-centroids[distance.argmin(-1)]


def reconstruction_loss(raw,target,positive_weights):
    # The executed prefix matters most, but all 32 ticks still train the codec.
    weights=raw.new_ones(32);weights[:8]=2.;weights=weights/weights.mean()
    continuous=((raw[...,:5].tanh()-target[...,:5])**2).mean(-1)
    buttons=F.binary_cross_entropy_with_logits(raw[...,5:],target[...,5:],
        pos_weight=positive_weights,reduction='none')
    buttons=(buttons*raw.new_tensor([4.,2.,1.])).mean(-1)
    return ((continuous+buttons)*weights).mean()


def controls_from_raw(raw,thresholds=0.):
    return torch.cat((raw[...,:5].tanh(),(raw[...,5:]>thresholds).to(raw.dtype)),-1)


def calibrate_buttons(raw,target):
    """Fit per-button thresholds on validation prefixes, never the test split."""
    thresholds=[]
    for axis in range(3):
        logits=raw[:,:8,5+axis].reshape(-1);truth=target[:,:8,5+axis].reshape(-1)>.5
        if not truth.any():thresholds.append(logits.new_zeros(()));continue
        order=logits.argsort(descending=True);sorted_logits=logits[order];labels=truth[order]
        true_positive=labels.cumsum(0);selected=torch.arange(1,len(labels)+1,device=logits.device)
        f1=2*true_positive/(truth.sum()+selected)
        valid=torch.cat((sorted_logits[:-1]!=sorted_logits[1:],torch.ones(1,device=logits.device,dtype=torch.bool)))
        choices=valid.nonzero()[:,0];best=int(choices[f1[choices].argmax()])
        left=sorted_logits[best];right=sorted_logits[best+1] if best+1<len(labels) else left-1
        threshold=(left+right)/2
        if threshold>=left:threshold=torch.nextafter(left,right)
        thresholds.append(threshold)
    return torch.stack(thresholds)


class StatePolicy(nn.Module):
    def __init__(self,codec=None,*,context=256,hidden=1024,spatial=None):
        super().__init__();self.codec=codec or ActionCodec()
        if self.codec.levels!=4 or self.codec.codes!=64:raise ValueError('This policy requires four residual codebooks with 64 codes each')
        self.spatial=spatial if spatial is not None else Encoder()
        self.context=nn.Sequential(nn.Linear(128,hidden),nn.GELU(),nn.Linear(hidden,hidden),nn.GELU(),
            nn.Linear(hidden,context),nn.LayerNorm(context))
        self.embeddings=nn.ModuleList([nn.Embedding(self.codec.codes,128) for _ in range(self.codec.levels-1)])
        self.cell=nn.GRUCell(128,context)
        self.heads=nn.ModuleList([nn.Linear(context,self.codec.codes) for _ in range(self.codec.levels)])
        self.values=nn.ModuleList([nn.Sequential(nn.Linear(context,128),nn.GELU(),nn.Linear(128,1)) for _ in range(3)])
        self.offset=nn.Sequential(nn.Linear(context+self.codec.latent,512),nn.GELU(),nn.Linear(512,160))
        nn.init.zeros_(self.offset[-1].weight);nn.init.zeros_(self.offset[-1].bias)
        self.config={'context':context,'hidden':hidden,'codec':self.codec.config}

    def encode(self,observations):
        q,kv,mask=observations
        # Root live packets do not expose opponents' actual previous buttons.
        # Train and deploy on the same observable physics instead of relying
        # on replay-only controls that disappear when forecasting other cars.
        q=torch.cat((q[...,:24],torch.zeros_like(q[...,24:])),dim=-1)
        return self.context(self.spatial((q,kv,mask)))
    def value(self,features):return torch.cat([head(features).tanh() for head in self.values],-1)

    def teacher_logits(self,features,codes):
        h=features;logits=[]
        for level in range(self.codec.levels):
            if level:h=self.cell(self.embeddings[level-1](codes[:,level-1]),h)
            logits.append(self.heads[level](h))
        return torch.stack(logits,1)

    def raw_actions(self,features,codes):
        z=self.codec.latent_from_codes(codes);raw=self.codec.decode_latent(z)
        offset=.05*self.offset(torch.cat((features,z),-1)).tanh().reshape(-1,32,5)
        # Offset only analogue controls, never fractional jump/boost buttons.
        continuous=(raw[...,:5].tanh()+offset).clamp(-1,1)
        return torch.cat((continuous,raw[...,5:]),-1)

    def actions(self,features,codes):
        raw=self.raw_actions(features,codes)
        return torch.cat((raw[...,:5],(raw[...,5:]>self.codec.button_thresholds).to(raw.dtype)),-1)

    def greedy(self,features):
        h=features;labels=[];logp=features.new_zeros(features.shape[0])
        for level in range(self.codec.levels):
            if level:h=self.cell(self.embeddings[level-1](labels[-1]),h)
            logits=self.heads[level](h);code=logits.argmax(-1);labels.append(code)
            logp=logp+logits.log_softmax(-1).gather(1,code[:,None])[:,0]
        codes=torch.stack(labels,-1)
        return self.actions(features,codes),codes,logp

    def propose(self,features):
        """64 fixed lines: top-16 first codes x top-4 second; then argmax."""
        batch=features.shape[0]
        first_logp,first=self.heads[0](features).log_softmax(-1).topk(16,-1)
        h=features[:,None].expand(-1,16,-1).reshape(batch*16,-1)
        h=self.cell(self.embeddings[0](first.reshape(-1)),h)
        second_logp,second=self.heads[1](h).log_softmax(-1).topk(4,-1)
        h=h[:,None].expand(-1,4,-1).reshape(batch*64,-1)
        first=first[:,:,None].expand(-1,-1,4).reshape(batch*64)
        labels=[first,second.reshape(-1)]
        logp=(first_logp.reshape(batch*16,1)+second_logp).reshape(batch*64)
        for level in range(2,self.codec.levels):
            h=self.cell(self.embeddings[level-1](labels[-1]),h)
            logits=self.heads[level](h);code=logits.argmax(-1);labels.append(code)
            logp=logp+logits.log_softmax(-1).gather(1,code[:,None])[:,0]
        codes=torch.stack(labels,-1)
        repeated=features[:,None].expand(-1,64,-1).reshape(batch*64,-1)
        actions=self.actions(repeated,codes).reshape(batch,64,32,8)
        codes=codes.reshape(batch,64,self.codec.levels);logp=logp.reshape(batch,64)
        order=logp.argsort(-1,descending=True)
        return (actions.gather(1,order[:,:,None,None].expand(-1,-1,32,8)),
            codes.gather(1,order[:,:,None].expand(-1,-1,self.codec.levels)),logp.gather(1,order))
