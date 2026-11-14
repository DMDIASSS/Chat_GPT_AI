"""Bounded execution tuning on the actual machine. No probe weights are kept."""
import copy,gc,json,math,time
from pathlib import Path
import numpy as np
import torch
from torch.distributions import Categorical
from .runtime import ROOT,config,device,batch,atomic_json
from .observation import encode
from .model import ActorCritic
from .performance import sample_actions
from .execution import make_optimizer,compile_checked

def probe(cfg,steps=16):
    torch.set_num_threads(cfg['torch_threads']);dev=device(cfg);torch.manual_seed(cfg['seed'])
    model=ActorCritic(**cfg['network']).to(dev).eval()
    # Fixed eager path in the first arena sweep; GPU_PROFILE compares execution
    # backends and larger optimizer batches using the trained checkpoint.
    env=batch(cfg);loc=env.pad_locations();raw=env.observe();n=cfg['n_envs'];a=2*cfg['team_size']
    peak=0
    def sync():
        if dev.type=='cuda':torch.cuda.synchronize(dev)
    if dev.type=='cuda':torch.cuda.reset_peak_memory_stats(dev)
    with torch.no_grad():
        for t in range(steps+4):
            if t==4:sync();start=time.perf_counter()
            ob,lm=encode(raw['world'],raw['pads'],loc);x=torch.as_tensor(ob.reshape(-1,43,40),device=dev);legal=torch.as_tensor(lm.reshape(-1,90),device=dev);logits,v=model(x,legal);ac,lp=sample_actions(logits)
            packed=torch.stack((ac.float(),lp,v),-1).cpu().numpy();raw=env.step(packed[:,0].astype(np.int64).reshape(n,a))
        sync();collection=time.perf_counter()-start
    model.train();opt,_=make_optimizer(model,cfg,dev)
    size=cfg['ppo']['batch_size'];index=np.arange(size)%(n*a);tx=x[index].clone();tl=legal[index].clone();old_logits,old_values=model(tx,tl);action,old_lp=sample_actions(old_logits.detach());target=old_values.detach()+torch.linspace(-.2,.2,size,device=dev);adv=torch.linspace(-1,1,size,device=dev)
    del old_logits,old_values
    # Same clipped PPO loss, value and entropy terms as training, on synthetic
    # fixed targets. This is an optimizer timing/memory test, not a strength test.
    for k in range(3):
        if k==1:sync();learn_start=time.perf_counter()
        lg,value=model(tx,tl);d=Categorical(logits=lg,validate_args=False);ratio=(d.log_prob(action)-old_lp).exp();loss=-torch.minimum(adv*ratio,adv*ratio.clamp(.8,1.2)).mean()+cfg['ppo']['value']*.5*(value-target).square().mean()-cfg['ppo']['entropy']*d.entropy().mean()
        if not torch.isfinite(loss):raise FloatingPointError('Nonfinite tuning loss')
        opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),cfg['ppo']['max_grad_norm'],error_if_nonfinite=True);opt.step()
    sync();learn=(time.perf_counter()-learn_start)/2
    total=n*a*cfg['ppo']['steps'];estimated=total/(collection/steps*cfg['ppo']['steps']+math.ceil(total/size)*cfg['ppo']['epochs']*learn)
    if dev.type=='cuda':peak=torch.cuda.max_memory_allocated(dev)/1024**2
    result={'arenas':n,'native_threads':cfg['native_threads'],'torch_threads':cfg['torch_threads'],'device':str(dev),'inference_and_simulation_player_sps':steps*n*a/collection,'optimizer_minibatch_seconds':learn,'estimated_full_ppo_learning_sps':estimated,'peak_probe_cuda_mb':peak,'host_rollout_mb':total*(43*40*4+90+32)/1024**2,'sample_steps':steps,'method':'16 collection steps after warmup plus 2 optimizer minibatches; full-update throughput is estimated, not measured'}
    del model,opt,env,tx,tl,x,legal;gc.collect()
    if dev.type=='cuda':torch.cuda.empty_cache()
    return result

def tune(template=None,quick=False):
    base=config(template or ROOT/'laptop_config.json');rows=[]
    print('LAPTOP_TUNING: fresh disposable 1.09M model; FP32; no existing models or CUDA packages are changed.',flush=True)
    def attempt(c):
        label={k:c[k] for k in ('n_envs','native_threads','torch_threads')};print('TUNE_PROBE:',label,flush=True)
        try:
            row=probe(c,steps=8 if quick else 16);row['config']=c;rows.append(row);print('TUNE_RESULT: estimated',round(row['estimated_full_ppo_learning_sps']),'learning transitions/s; rollout',round(row['inference_and_simulation_player_sps']),'player decisions/s',flush=True)
        except torch.OutOfMemoryError:
            print('TUNE_SKIPPED: this probe exceeded available GPU memory; trying smaller settings.',flush=True);gc.collect();torch.cuda.empty_cache()
    for n in ((32,64) if quick else (32,64,128)):
        c=copy.deepcopy(base);c['n_envs']=n;attempt(c)
    if not rows:raise RuntimeError('No tuning probe fit. Close other GPU programs and retry.')
    best=max(rows,key=lambda x:x['estimated_full_ppo_learning_sps'])
    if not quick:
        for field,value in (('native_threads',2),('torch_threads',1)):
            c=copy.deepcopy(best['config']);c[field]=value;attempt(c)
    fastest=max(x['estimated_full_ppo_learning_sps'] for x in rows)
    # Prefer fewer arenas/workers within 5% of the timing winner.
    eligible=[x for x in rows if x['estimated_full_ppo_learning_sps']>=fastest*.95]
    winner=min(eligible,key=lambda x:(x['arenas'],x['native_threads']+x['torch_threads']))
    chosen=winner['config'];atomic_json(ROOT/'laptop_tuned.json',chosen)
    result={'version':'attentionforge-laptop-tune-v1','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'gpu':torch.cuda.get_device_name(0) if device(base).type=='cuda' else None,'selected':{k:v for k,v in winner.items() if k!='config'},'probes':[{k:v for k,v in row.items() if k!='config'} for row in rows],'limitations':['Small timing probes are noisy and their full-PPO rate is an estimate. Confirm with actual training metrics.','Arena count changes samples per PPO update. Playing strength is not evaluated by tuning.','No training epochs, tick skip, action delay, model size, reward weights or numeric precision are reduced for speed.']}
    atomic_json(ROOT/'laptop_autotune.json',result);print('LAPTOP_CONFIG_READY:',ROOT/'laptop_tuned.json',flush=True);return chosen
