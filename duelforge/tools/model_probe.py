"""Bounded synthetic model/optimizer probe. No game training or checkpoints."""
import argparse,json,platform,time,statistics,sys
from pathlib import Path
import torch
from torch import nn

class Dense(nn.Module):
    def __init__(self,width=512):
        super().__init__()
        def head(output):
            layers=[];size=109
            for _ in range(3):layers.extend([nn.Linear(size,width),nn.LayerNorm(width),nn.ReLU()]);size=width
            return nn.Sequential(*layers,nn.Linear(width,output))
        self.actor=head(90);self.critic=head(1)
    def forward(self,x):return self.actor(x),self.critic(x).squeeze(-1)

class EntityAttention(nn.Module):
    """Four tokens: ball(9), ego(29), rival(29), globals(pads34+controls8).
    Synthetic throughput comparison only; no competitive equivalence is claimed.
    """
    def __init__(self):
        super().__init__();w=256
        self.ball=nn.Linear(9,w);self.car=nn.Linear(29,w);self.global_input=nn.Linear(42,w);self.types=nn.Parameter(torch.zeros(4,w))
        layer=nn.TransformerEncoderLayer(w,4,512,dropout=0,batch_first=True,norm_first=True)
        self.encoder=nn.TransformerEncoder(layer,2,enable_nested_tensor=False)
        self.actor=nn.Sequential(nn.Linear(w,256),nn.ReLU(),nn.Linear(256,90));self.critic=nn.Sequential(nn.Linear(w,256),nn.ReLU(),nn.Linear(256,1))
    def forward(self,x):
        tokens=torch.stack([self.ball(x[:,:9]),self.car(x[:,51:80]),self.car(x[:,80:109]),self.global_input(x[:,9:51])],dim=1)+self.types
        z=self.encoder(tokens)[:,1];return self.actor(z),self.critic(z).squeeze(-1)

MODELS={'dense512':lambda:Dense(512),'dense768':lambda:Dense(768),'attention4':EntityAttention}

def sync(device):
    if device.type=='cuda':torch.cuda.synchronize(device)

def percentile(values,q):return sorted(values)[min(len(values)-1,int((len(values)-1)*q))]

def measure(name,device,batch,seconds,train=False):
    torch.manual_seed(1);model=MODELS[name]().to(device);x=torch.randn(batch,109,device=device)
    model.train(train);optimizer=torch.optim.Adam(model.parameters(),lr=1e-4) if train else None
    labels=torch.randint(0,90,(batch,),device=device);target=torch.randn(batch,device=device)
    def step():
        if train:
            logits,v=model(x);loss=nn.functional.cross_entropy(logits,labels)+.5*(v-target).square().mean();optimizer.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),.5,error_if_nonfinite=True);optimizer.step()
        else:
            with torch.inference_mode():model(x)
    for _ in range(3):step()
    sync(device)
    if device.type=='cuda':torch.cuda.reset_peak_memory_stats(device)
    samples=[];start=time.perf_counter()
    while time.perf_counter()-start<seconds or len(samples)<5:
        t=time.perf_counter();step();sync(device);samples.append(time.perf_counter()-t)
    elapsed=time.perf_counter()-start
    return {'model':name,'parameters':sum(p.numel() for p in model.parameters()),'device':str(device),'phase':'synthetic_forward_backward_adam' if train else 'actor_and_critic_inference','batch':batch,'iterations':len(samples),'seconds':elapsed,'examples_per_second':batch*len(samples)/elapsed,'p50_ms':statistics.median(samples)*1000,'p95_ms':percentile(samples,.95)*1000,'gpu_peak_allocated_mb':torch.cuda.max_memory_allocated(device)/2**20 if device.type=='cuda' else None,'gpu_peak_reserved_mb':torch.cuda.max_memory_reserved(device)/2**20 if device.type=='cuda' else None,'note':'Synthetic tensors; excludes simulator, encoding and transfers. Not SPS or playing strength.'}

def run(output,seconds=1.,threads=2,quick=False):
    torch.set_num_threads(threads);device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('DEVICE:',device,'GPU:',torch.cuda.get_device_name() if device.type=='cuda' else 'none; CPU-only probe',flush=True)
    rows=[]
    for name in MODELS:
        cases=[(1,False),(256,False),(1024,True)]
        if not quick:cases.extend([(2048,True),(4096,True)])
        for batch,train in cases:
            try:
                row=measure(name,device,batch,seconds,train);rows.append(row)
                print(name,row['phase'],'batch',batch,round(row['examples_per_second']),'examples/s;',round(row['p95_ms'],2),'ms p95',flush=True)
            except torch.cuda.OutOfMemoryError:
                rows.append({'model':name,'batch':batch,'phase':'train' if train else 'inference','error':'CUDA_OOM','note':'Probe stopped at this size; no training/model artifacts exist'});torch.cuda.empty_cache();break
    result={'kind':'bounded_synthetic_probe','torch':torch.__version__,'python':sys.version,'platform':platform.platform(),'threads':threads,'cuda_available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name() if device.type=='cuda' else None,'gpu_capability':torch.cuda.get_device_capability() if device.type=='cuda' else None,'gpu_total_mb':torch.cuda.get_device_properties(device).total_memory/2**20 if device.type=='cuda' else None,'precision':'FP32','results':rows,'scope':'Architecture cost probe, not a complete training framework benchmark; results are machine-specific.'}
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print('REPORT:',out.resolve(),flush=True);return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='results/model_probe.json');ap.add_argument('--seconds',type=float,default=1);ap.add_argument('--threads',type=int,default=2);ap.add_argument('--quick',action='store_true');a=ap.parse_args()
    if not .1<=a.seconds<=5 or not 1<=a.threads<=4:ap.error('Bounded probe requires seconds 0.1..5 and threads 1..4')
    run(a.output,a.seconds,a.threads,a.quick)
