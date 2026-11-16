import torch
from functools import lru_cache
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
