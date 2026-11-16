"""Brief neural warm-up from verified no-boost flip demonstrations."""
import copy,json,os,shutil
from pathlib import Path
import numpy as np
import torch
from .runtime import load,save,model,device,atomic_json,sha
from .ground_flip import GroundFlipBatch,NEUTRAL
from .flip_experiment import balanced_cases,install_cases,probe,DRIVE,JUMP,DODGE
from .runtime import batch
from .jump_bootstrap import normal_data,tensor_features

def demonstrations(cfg,pairs=64,seed=0xE2100000):
    e=GroundFlipBatch(batch(cfg,n=2*pairs,seconds=5),cfg,seed,force=True)
    w,col=balanced_cases(seed,pairs);install_cases(e,w,col);raw=e.observe();n=len(w);ix=np.arange(n)
    done=np.zeros(n,bool);success=done.copy();records=[]
    for t in range(33):
        choice=DRIVE if t<14 else JUMP if t==14 else DODGE if t==16 else NEUTRAL
        action=np.full((n,2),NEUTRAL,np.int64);action[ix,col]=choice;active=~done
        records.append((raw['obs'][ix,col].copy(),raw['mask'][ix,col].copy(),np.full(n,choice,np.int64),active.copy(),np.full(n,13<=t<=17)))
        raw=e.step(action,np.where(done,0,8));r=raw['flip_drill'];success|=r['success']&active;done|=r['completed']
        if done.all():break
    if success.sum()<n*.9:raise RuntimeError('Too few physically successful flip demonstrations; no guessed labels used')
    out=[]
    for field in (0,1,2,4):out.append(np.concatenate([row[field][row[3]&success] for row in records]))
    x,l,a,critical=out
    if not l[np.arange(len(a)),a].all():raise ValueError('Demonstration violates native/drill mask')
    return x,l,a,critical

def candidate(template,m,step,kl):
    child=copy.deepcopy(template);child['model']={k:v.detach().cpu().clone() for k,v in m.state_dict().items()}
    names=[name for name,_ in m.named_parameters()];ids=[i for group in child['optimizer']['param_groups'] for i in group['params']]
    if len(names)!=len(ids):raise ValueError('Optimizer parameter mapping changed')
    for name,index in zip(names,ids):
        if name.startswith(('actor.6.','actor.7.','actor.9.')):child['optimizer']['state'].pop(index,None)
    child['flip_bootstrap']={'updates':step,'normal_policy_kl':kl,'rl_steps_added':0}
    return child

def fit(root,updates=300):
    root=Path(root);folder=root/'03_trajectory';templatefile=root/'flip_warmup_template.pt'
    if not templatefile.exists():save(templatefile,load(folder/'latest.pt'))
    template=load(templatefile);c=template['config'];dev=device(c);torch.set_num_threads(c['torch_threads'])
    source,_,_=model(root,checkpoint=root/'baseline.pt',dev=dev);m,_,_=model(folder,dev=dev)
    cache=root/'flip_warmup_data.npz'
    if not cache.exists():
        x,l,a,critical=demonstrations(c);gx,gl,gp=normal_data(source,c,seed=0xE2200000)
        np.savez_compressed(cache,x=x,l=l,a=a,critical=critical,gx=gx,gl=gl,gp=gp)
    data=np.load(cache);x,l,a,critical=[data[k] for k in ('x','l','a','critical')]
    gx,gl,gp=[data[k] for k in ('gx','gl','gp')]
    xf=tensor_features(m.actor,x,dev);gf=tensor_features(m.actor,gx,dev)
    lm=torch.as_tensor(l,device=dev);labels=torch.as_tensor(a,device=dev);glm=torch.as_tensor(gl,device=dev);gprob=torch.as_tensor(gp,device=dev)
    for param in m.parameters():param.requires_grad_(False)
    for param in m.actor[6:].parameters():param.requires_grad_(True)
    opt=torch.optim.Adam(m.actor[6:].parameters(),lr=.001);rng=np.random.default_rng(0xE2400000)
    start=0;best=probe(folder/'latest.pt',seed=0xE2300000)['success_rate'];bestkl=0.;statefile=root/'flip_warmup_state.pt';critical_ids=np.flatnonzero(critical)
    if statefile.exists():
        s=load(statefile);m.load_state_dict(s['model']);opt.load_state_dict(s['optimizer']);rng.bit_generator.state=s['rng']
        start=s['updates'];best=s['best'];bestkl=s['best_kl']
    for step in range(start,updates):
        if (root/'STOP').exists():return False
        ids=np.concatenate([rng.integers(len(x),size=128),rng.choice(critical_ids,size=128)])
        ii=torch.as_tensor(ids,device=dev);gg=torch.as_tensor(rng.integers(len(gx),size=256),device=dev)
        logits=m.actor[6:](xf[ii]).masked_fill(~lm[ii],-1e9)
        retained=m.actor[6:](gf[gg]).masked_fill(~glm[gg],-1e9).log_softmax(-1)
        ce=torch.nn.functional.cross_entropy(logits,labels[ii]);kl=torch.nn.functional.kl_div(retained,gprob[gg],reduction='batchmean')
        loss=ce+2*kl
        if not torch.isfinite(loss):raise FloatingPointError('Nonfinite flip warm-up loss; complete checkpoint preserved')
        opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(m.actor[6:].parameters(),1,error_if_nonfinite=True);opt.step()
        if (step+1)%25==0 or step+1==updates:
            with torch.inference_mode():
                retained=m.actor[6:](gf).masked_fill(~glm,-1e9).log_softmax(-1)
                normal_kl=max(0.,float(torch.nn.functional.kl_div(retained,gprob,reduction='batchmean').cpu()))
            trial=root/'flip_warmup_trial.pt';save(trial,candidate(template,m,step+1,normal_kl));validation=probe(trial,seed=0xE2300000)
            score=validation['success_rate']
            if normal_kl<=.05 and (score>best or (score==best and normal_kl<bestkl)):
                best=score;bestkl=normal_kl;save(folder/'latest.pt',load(trial))
            row={'logging_step':step+1,'learning_transitions':template['learning_transitions'],
                'flip_warmup/update':step+1,'flip_warmup/validation_success':score,'flip_warmup/normal_kl':normal_kl,
                'flip_warmup/best_success':best,'flip_warmup/loss':float(loss.detach().cpu())}
            with (folder/'metrics.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            save(statefile,{'model':m.state_dict(),'optimizer':opt.state_dict(),'updates':step+1,'best':best,'best_kl':bestkl,'rng':rng.bit_generator.state})
            print('FLIP_WARMUP:',step+1,'/',updates,'greedy success',round(score*100,1),'%; normal KL',round(normal_kl,4),flush=True)
    heldout=probe(folder/'latest.pt',seed=0xE2500000)
    accepted=heldout['success_rate']>=.5 and bestkl<=.05
    pin=root/'flip_warmup_accepted.pt'
    if accepted:
        temporary=root/'.flip_warmup_accepted.tmp';shutil.copy2(folder/'latest.pt',temporary);os.replace(temporary,pin)
    atomic_json(root/'flip_warmup_result.json',{'heldout':heldout,'best_validation':best,'normal_kl':bestkl,
       'candidate_sha256':sha(folder/'latest.pt'),'source_sha256':sha(root/'baseline.pt'),
       'accepted_checkpoint':'flip_warmup_accepted.pt' if accepted else None,
       'supervised_updates':updates,'reinforcement_learning_steps_added':0,'scope':'Neural head warm-up; real native demonstrations. No script in live policy.'})
    return accepted
