"""GPU execution choices with preserved model/Adam state and FP32 arithmetic."""
import copy,gc,math,time
from functools import lru_cache
import torch
from torch.distributions import Categorical

def configure_optimizer(opt,device,backend):
    """load_state_dict restores saved implementation flags: normalize them again.
    Keep learning rate, betas, epsilon, moments and step values unchanged.
    """
    for group in opt.param_groups:
        group['fused']=backend=='adam_fused';group['foreach']=backend=='adam_foreach'
        for p in group['params']:
            state=opt.state.get(p,{})
            if 'step' in state:
                target=device if group['fused'] or group.get('capturable',False) else torch.device('cpu')
                state['step']=torch.as_tensor(state['step'],dtype=torch.float32,device=target)
    return opt

@lru_cache(maxsize=8)
def optimizer_backend(device_name):
    device=torch.device(device_name)
    if device.type!='cuda':return 'adam_cpu'
    # Probe only a disposable tensor. Never discover unsupported fused kernels
    # by attempting an update of the user's trained model.
    for name,flags in [('adam_fused',dict(fused=True,foreach=False)),('adam_foreach',dict(fused=False,foreach=True))]:
        try:
            p=torch.nn.Parameter(torch.tensor([1.,-2.],device=device));p.grad=torch.tensor([.2,-.1],device=device)
            opt=torch.optim.Adam([p],lr=3e-4,eps=1e-5,**flags);opt.step();torch.cuda.synchronize(device)
            if not torch.isfinite(p).all():raise FloatingPointError('Nonfinite optimizer probe')
            return name
        except (TypeError,RuntimeError) as ex:
            print('OPTIMIZER_PROBE_SKIPPED:',name,type(ex).__name__,flush=True)
    raise RuntimeError('CUDA Adam probes failed; no trained weights were changed')

def make_optimizer(model,cfg,device):
    name=optimizer_backend(str(device))
    opt=torch.optim.Adam(model.parameters(),lr=cfg['ppo']['learning_rate'],eps=1e-5,fused=name=='adam_fused',foreach=name=='adam_foreach')
    return opt,name

def compile_checked(model):
    """Script the standard PyTorch model; preserve exact Parameter objects."""
    scripted=torch.jit.script(model)
    a=list(model.named_parameters());b=list(scripted.named_parameters())
    if len(a)!=len(b) or any(n!=m or p is not q for (n,p),(m,q) in zip(a,b)):
        raise RuntimeError('Scripted model did not preserve optimizer parameter identity')
    return scripted

def optimizer_probe(source,cfg,device,batch_size,scripted=False,warmup=3,repeats=3):
    """Disposable same-shape PPO updates; no rollout labels or probe weights kept."""
    model=copy.deepcopy(source).to(device).train()
    if scripted:model=compile_checked(model)
    opt,backend=make_optimizer(model,cfg,device)
    # A repeated public observation is sufficient for timing dense operations.
    tokens=torch.zeros(batch_size,43,40,device=device);tokens[:,:,39]=5;tokens[:,0,39]=1;tokens[:,1,39]=2
    legal=torch.ones(batch_size,90,device=device,dtype=torch.bool)
    with torch.no_grad():
        old_logits,old_value=model(tokens,legal);action=old_logits.argmax(-1)
        old_lp=old_logits.log_softmax(-1).gather(1,action[:,None]).squeeze(1)
        target=old_value+torch.linspace(-.3,.3,batch_size,device=device);adv=torch.linspace(-1,1,batch_size,device=device)
    def sync():
        if device.type=='cuda':torch.cuda.synchronize(device)
    if device.type=='cuda':torch.cuda.reset_peak_memory_stats(device)
    times=[]
    for k in range(warmup+repeats):
        sync();start=time.perf_counter()
        logits,value=model(tokens,legal);d=Categorical(logits=logits,validate_args=False)
        logratio=d.log_prob(action)-old_lp;ratio=logratio.exp();kl=((ratio-1)-logratio).mean()
        loss=-torch.minimum(adv*ratio,adv*ratio.clamp(1-cfg['ppo']['clip'],1+cfg['ppo']['clip'])).mean()+cfg['ppo']['value']*.5*(value-target).square().mean()-cfg['ppo']['entropy']*d.entropy().mean()
        opt.zero_grad(set_to_none=True);loss.backward()
        norm=torch.nn.utils.clip_grad_norm_(model.parameters(),cfg['ppo']['max_grad_norm'],error_if_nonfinite=False)
        health=torch.stack((loss.detach(),kl.detach(),norm.detach())).cpu()
        if not torch.isfinite(health).all():raise FloatingPointError('Nonfinite disposable GPU probe')
        opt.step();sync()
        if k>=warmup:times.append(time.perf_counter()-start)
    peak=torch.cuda.max_memory_allocated(device)/1024**2 if device.type=='cuda' else 0
    result={'batch_size':batch_size,'execution':'torchscript' if scripted else 'eager','optimizer':backend,'median_minibatch_seconds':float(sorted(times)[len(times)//2]),'optimizer_samples_per_second':batch_size/(sum(times)/len(times)),'peak_probe_cuda_mb':peak,'repeats':repeats,'scope':'Synthetic PPO minibatch timing, not new experience/s or a learning-strength measurement'}
    del opt,model,tokens,legal;gc.collect()
    return result

def select_model_execution(model,cfg,device):
    """Auto uses the actual GPU; CPU remains eager. Never changes model weights."""
    setting=cfg.get('performance',{}).get('model_execution','auto')
    if setting=='eager' or (setting=='auto' and device.type!='cuda'):return model,'eager',[]
    if setting=='torchscript':return compile_checked(model),'torchscript',[]
    if setting!='auto':raise ValueError('model_execution must be auto, eager or torchscript')
    rows=[]
    for scripted in (False,True):
        try:
            row=optimizer_probe(model,cfg,device,min(256,cfg['ppo']['batch_size']),scripted);rows.append(row)
        except (RuntimeError,TypeError) as ex:
            print('MODEL_PROBE_SKIPPED:', 'torchscript' if scripted else 'eager',type(ex).__name__,flush=True)
        gc.collect();torch.cuda.empty_cache()
    eager=next((r for r in rows if r['execution']=='eager'),None);script=next((r for r in rows if r['execution']=='torchscript'),None)
    use_script=script is not None and eager is not None and script['median_minibatch_seconds']<eager['median_minibatch_seconds']*.95
    if use_script:
        try:
            compiled=compile_checked(model)
            # Check logits/value agreement on the actual device before training.
            x=torch.zeros(2,43,40,device=device);x[:,0,39]=1;x[:,1,39]=2;mask=torch.ones(2,90,dtype=torch.bool,device=device)
            with torch.no_grad():
                a,v=model(x,mask);b,z=compiled(x,mask);torch.testing.assert_close(a,b,rtol=1e-4,atol=1e-5);torch.testing.assert_close(v,z,rtol=1e-4,atol=1e-5)
            return compiled,'torchscript',rows
        except (RuntimeError,AssertionError) as ex:print('MODEL_PROBE_FALLBACK:',type(ex).__name__,flush=True)
    return model,'eager',rows

def checked_step(loss,kl,model,opt,max_norm,target_kl):
    """Retain finite/KL/gradient gates, with one pre-update host synchronization."""
    opt.zero_grad(set_to_none=True);loss.backward()
    norm=torch.nn.utils.clip_grad_norm_(model.parameters(),max_norm,error_if_nonfinite=False)
    health=torch.stack((kl.detach(),loss.detach(),norm.detach())).cpu()
    if not torch.isfinite(health).all():
        opt.zero_grad(set_to_none=True)
        raise FloatingPointError('Nonfinite PPO loss/KL/gradient; no optimizer step was taken')
    if float(health[0])>target_kl*1.5:
        opt.zero_grad(set_to_none=True);return False,norm.detach()
    opt.step();return True,norm.detach()
