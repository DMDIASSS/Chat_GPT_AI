"""Optional frozen Nexto neural adapter. No stock scripted kickoff is added.
Vectorized features are tested against the pinned upstream NextoObsBuilder.
"""
import hashlib,json,urllib.request
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,sha,atomic_json
BASE='https://raw.githubusercontent.com/RLBot/RLBotPack/0033a98d4e060670f334f60f7f8dc5ee21ba93bb/RLBotPack/Necto/'
FILES={'policy.pt':('Nexto/nexto-model.pt','bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa'),'nexto_obs.py':('Nexto/nexto_obs.py','7247046d836059ab4428fb8f08968af1a977cf3228f1462a0235cd7a825362b0'),'LICENSE':('LICENSE','1349a4b6148492b44f629e64eed676612e234fe9a839e4f3b277c1482c8849f1')}

def fetch():
    target=ROOT/'assets/nexto';target.mkdir(parents=True,exist_ok=True)
    for name,(rel,h) in FILES.items():
        path=target/name
        if path.is_file() and sha(path)==h:continue
        print('FETCHING_NEXT0_ASSET:',name,flush=True)
        with urllib.request.urlopen(BASE+rel,timeout=60) as r:data=r.read(32*1024*1024)
        if hashlib.sha256(data).hexdigest()!=h:raise ValueError('Nexto asset checksum differs: '+name)
        temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(data);temp.replace(path)
    atomic_json(target/'identity.json',{'name':'Nexto neural policy','source':BASE,'files':{k:v[1] for k,v in FILES.items()},'scripted_kickoff':False});return target


def observations(world,pads,locations,color):
    world=np.asarray(world,dtype=np.float64);pads=np.asarray(pads);n=len(world);kv=np.zeros((n,37,24),np.float64)
    kv[:,2,3]=1;kv[:,2,5:11]=world[:,0,:6];kv[:,2,17:20]=world[:,0,6:9]
    kv[:,3:,4]=1;kv[:,3:,5:8]=locations[None,:,:3];kv[:,3:,20]=.12+.88*(locations[None,:,2]>72);kv[:,3:,21]=pads[:,:,0]
    for a in (0,1):
        c=world[:,a+1];kv[:,a,1 if a==0 else 2]=1;kv[:,a,5:11]=c[:,:6];kv[:,a,11:17]=c[:,9:15];kv[:,a,17:20]=c[:,6:9];kv[:,a,20]=c[:,15]/100;kv[:,a,21]=c[:,20];kv[:,a,22]=c[:,16];kv[:,a,23]=c[:,29]
    kv[:,color,0]=1
    if color:
        invert=np.array([1]*5+[-1,-1,1]*5+[1]*4);kv*=invert;kv[:,:,[1,2]]=kv[:,:,[2,1]]
    norm=np.array([1]*5+[2300]*6+[1]*6+[5.5]*3+[1]*4);kv/=norm
    q=np.zeros((n,1,32),np.float64);q[:,0,:24]=kv[:,color];q[:,0,24:32]=world[:,color+1,21:29]
    # Same relative rotation and order as upstream convert_to_relative.
    kv[:,:,5:8]-=q[:,:,5:8];theta=np.arctan2(q[:,:,11],q[:,:,12]);ct=np.cos(theta)[:,:,None];st=np.sin(theta)[:,:,None]
    x=kv[:,:,5:20:3];y=kv[:,:,6:20:3];nx=ct*x-st*y;ny=st*x+ct*y;kv[:,:,5:20:3]=nx;kv[:,:,6:20:3]=ny
    return q.astype(np.float32),kv.astype(np.float32),np.zeros((n,37),np.float32)

class Nexto:
    def __init__(self,download=False):
        path=fetch() if download else ROOT/'assets/nexto'
        for name,(_,h) in FILES.items():
            if not (path/name).is_file() or sha(path/name)!=h:raise FileNotFoundError('Verified Nexto assets missing; run 10_FETCH_NEXTO.bat. No substitute opponent was selected.')
        self.identity=FILES['policy.pt'][1];self.model=torch.jit.load(str(path/'policy.pt'),map_location='cpu').eval()
    def act(self,raw,locations,colors):
        colors=np.asarray(colors);n=len(raw['world']);out=np.empty(n,np.int64)
        with torch.inference_mode():
            for color in (0,1):
                ix=np.flatnonzero(colors==color)
                if not len(ix):continue
                ob=observations(raw['world'][ix],raw['pads'][ix],locations,color);result=self.model(tuple(torch.from_numpy(x) for x in ob));logits=result[0] if isinstance(result,tuple) else result
                if logits.shape!=(len(ix),90) or not torch.isfinite(logits).all():raise RuntimeError('Invalid Nexto logits')
                out[ix]=logits.argmax(-1).numpy()
        return out
