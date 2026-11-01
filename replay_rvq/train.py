"""Separate, resumable, supervised codec/policy stages using cached human data."""
from pathlib import Path
from importlib.metadata import version
import random,time,hashlib
import numpy as np
import torch
from torch.nn import functional as F
from replay_il.train import batches,save
from replay_il.monitor import Monitor
from replay_rvq.model import ActionCodec,StatePolicy,reconstruction_loss,controls_from_raw,calibrate_buttons
from replay_rvq.data import RVQData,sample_controls,positive_weights,epoch_rows
from slater_v041_core import sha256,read_json,atomic_json,process_lock

ROOT=Path(__file__).resolve().parents[1]


def source_identity():
    files=['replay_rvq/model.py','replay_rvq/data.py','replay_rvq/train.py',
        'replay_il/model.py','replay_il/train.py','replay_il/monitor.py','slater_v041_core.py']
    return {name:sha256(ROOT/name) for name in files}


def button_metrics(predicted,target):
    result={}
    for name,axis in (('jump',5),('boost',6),('handbrake',7)):
        truth=target[:,:8,axis]>.5;guess=predicted[:,:8,axis]>.5
        tp=int((truth&guess).sum());fp=int((~truth&guess).sum());fn=int((truth&~guess).sum())
        result[name]={'true_positive_ticks':tp,'false_positive_ticks':fp,'false_negative_ticks':fn,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
    return result


@torch.inference_mode()
def evaluate(model,data,stage,device,weights,batch_size=64,limit=4096):
    model.eval();count=0;loss=ce=value_mse=zero_mse=offset_mse=0.;predicted=[];targets=[];labels=[];correct=total_codes=0
    rows=epoch_rows(data.raw,'validation',limit=limit)
    for selected in batches(rows,batch_size):
        n=len(selected);count+=n
        if stage=='codec':
            target=data.take_controls(selected,device)
            raw,codes,_=model(target);decoded=controls_from_raw(raw,model.button_thresholds)
            loss+=float(reconstruction_loss(raw,target,weights))*n
        else:
            obs,target,codes,value,bootstrap=data.take(selected,device)
            features=model.encode(obs);logits=model.teacher_logits(features,codes)
            ce+=float(F.cross_entropy(logits.reshape(-1,model.codec.codes),codes.reshape(-1)))*n
            decoded,pred_codes,_=model.greedy(features)
            correct+=int((pred_codes==codes).sum());total_codes+=codes.numel()
            predicted_value=model.value(features).mean(-1)
            value_mse+=float(((predicted_value-value)**2).sum());zero_mse+=float((value**2).sum())
            offset_mse+=float(((model.raw_actions(features,codes)[...,:5]-target[...,:5])**2).mean())*n
        predicted.append(decoded.cpu());targets.append(target.cpu());labels.append(codes.cpu())
    if not count:raise ValueError('No independent validation samples')
    predicted=torch.cat(predicted);targets=torch.cat(targets);labels=torch.cat(labels)
    prefix=float(((predicted[:,:8]-targets[:,:8])**2).mean())
    report={'samples':count,'first8_control_mse':prefix,'buttons':button_metrics(predicted,targets),
        'predicted_first8_no_throttle_boost_fraction':float(((predicted[:,:8,0].abs().amax(1)<=.05)&(~(predicted[:,:8,6]>.5).any(1))).float().mean()),
        'target_first8_no_throttle_boost_fraction':float(((targets[:,:8,0].abs().amax(1)<=.05)&(~(targets[:,:8,6]>.5).any(1))).float().mean()),
        'competitive_strength_verified':False}
    if stage=='codec':
        usage=[torch.bincount(labels[:,i],minlength=model.codes).tolist() for i in range(model.levels)]
        report.update(reconstruction_loss=loss/count,code_usage=usage,
            codes_used=[sum(n>0 for n in row) for row in usage],score=loss/count)
    else:report.update(token_ce=ce/count,code_accuracy=correct/total_codes,value_mse=value_mse/count,
        constant_zero_value_mse=zero_mse/count,teacher_forced_offset_mse=offset_mse/count,
        score=ce/count+value_mse/count+prefix)
    return report


@torch.inference_mode()
def calibrate_codec(root,data,codec,weights,device,batch_size):
    folder=root/'codec';path=folder/'best.pt';existing=read_json(folder/'button_calibration.json',{})
    if existing.get('codec_sha256')==sha256(path):
        thresholds=torch.as_tensor(existing['thresholds'],device=device)
        if thresholds.shape!=(3,) or not torch.isfinite(thresholds).all():raise ValueError('Invalid saved button calibration')
        codec.button_thresholds.copy_(thresholds)
        return sha256(folder/'button_calibration.json')
    if (root/'policy/latest.pt').exists():raise ValueError('Frozen codec calibration changed/missing; preserve the run and restore its matching calibration')
    codec.eval();raw=[];targets=[]
    for rows in batches(epoch_rows(data.raw,'validation',limit=4096),batch_size):
        target=data.take_controls(rows,device);raw.append(codec(target)[0]);targets.append(target)
    raw=torch.cat(raw);targets=torch.cat(targets)
    before=button_metrics(controls_from_raw(raw,codec.button_thresholds),targets)
    codec.button_thresholds.copy_(calibrate_buttons(raw,targets))
    after=button_metrics(controls_from_raw(raw,codec.button_thresholds),targets)
    atomic_json(folder/'button_calibration.json',{'codec_sha256':sha256(path),'split':'validation','samples':len(targets),
        'thresholds':codec.button_thresholds.cpu().tolist(),'before':before,'after':after,
        'note':'Validation-fitted decision thresholds compensate weighted BCE; not test-set or gameplay evidence.'})
    print('RVQ_BUTTON_CALIBRATION:',after,flush=True)
    return sha256(folder/'button_calibration.json')


def stage_train(root,data,stage,*,epochs,device,weights,settings,config,batch_size=64,lr=2e-4,codec=None,codec_digest=None):
    folder=root/stage;latest=folder/'latest.pt';resume=latest.exists()
    if folder.exists() and not resume:raise ValueError('Stage initialization was interrupted. Preserve this run and choose a new name.')
    if stage=='codec':model=ActionCodec(**config['codec'])
    else:
        model=StatePolicy(codec,**config['policy'])
        for parameter in model.codec.parameters():parameter.requires_grad_(False)
    model.to(device)
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=lr,weight_decay=.01)
    progress={'epoch':0,'updates':0,'stale_epochs':0,'best_score':None}
    if resume:
        checkpoint=torch.load(latest,map_location='cpu',weights_only=True)
        if checkpoint['protocol_sha256']!=sha256(root/'protocol.json') or checkpoint.get('codec_sha256')!=codec_digest:
            raise ValueError('Stage checkpoint/configuration identity changed')
        model.load_state_dict(checkpoint['model']);optimizer.load_state_dict(checkpoint['optimizer']);progress=checkpoint['progress']
        torch.set_rng_state(checkpoint['torch_rng']);random.setstate(checkpoint['python_rng'])
        if checkpoint.get('cuda_rng') is not None and device=='cuda':torch.cuda.set_rng_state_all(checkpoint['cuda_rng'])
    elif stage=='codec':
        model.to(device).initialize(torch.as_tensor(sample_controls(data.raw),device=device))
    folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'model.json',{'stage':stage,'parameters':sum(p.numel() for p in model.parameters()),
        'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
        'input':'controls_only' if stage=='codec' else 'current_state_only','external_pretrained_weights_loaded':False})
    def checkpoint():
        return {'schema':'replay-rvq-stage-v1','stage':stage,'model':model.state_dict(),'optimizer':optimizer.state_dict(),
            'config':config,'progress':dict(progress),'protocol_sha256':sha256(root/'protocol.json'),'codec_sha256':codec_digest,
            'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if device=='cuda' else None,'python_rng':random.getstate()}
    if not resume:
        baseline=evaluate(model,data,stage,device,weights,batch_size)
        progress['best_score']=baseline['score'];save(latest,checkpoint());save(folder/'best.pt',checkpoint())
        atomic_json(folder/'selected.json',{'sha256':sha256(folder/'best.pt'),'validation':baseline,'epoch':0,'updates':0})
        atomic_json(folder/'validation_initial.json',baseline);atomic_json(folder/'progress.json',progress)
    if progress['epoch']>=epochs or progress['stale_epochs']>=4:
        print('RVQ_STAGE_COMPLETE:',stage,'saved epochs',progress['epoch'],'stale',progress['stale_epochs'],flush=True);return
    monitor=Monitor(folder,settings,read_json(root/'protocol.json'),prompt=True)
    try:
        while progress['epoch']<epochs and progress['stale_epochs']<4:
            if (root/'pause.flag').exists():return
            epoch=progress['epoch'];model.train();loss_sum=0.;seen=0;start=time.perf_counter();initial={n:p.detach().clone() for n,p in model.named_parameters() if p.requires_grad}
            for rows in batches(epoch_rows(data.raw,'train',epoch),batch_size):
                if (root/'pause.flag').exists():break
                if stage=='codec':
                    target=data.take_controls(rows,device)
                    raw,codes,vq=model(target);reconstruction=reconstruction_loss(raw,target,weights)
                    loss=reconstruction+.1*vq;metrics={'reconstruction':float(reconstruction.detach()),'vq':float(vq.detach())}
                else:
                    obs,target,codes,value,bootstrap=data.take(rows,device)
                    features=model.encode(obs);logits=model.teacher_logits(features,codes)
                    policy_loss=F.cross_entropy(logits.reshape(-1,model.codec.codes),codes.reshape(-1))
                    values=model.value(features);value_loss=(((values-value[:,None])**2)*bootstrap).sum()/bootstrap.sum().clamp_min(1)
                    raw=model.raw_actions(features,codes);offset_loss=((raw[...,:5]-target[...,:5])**2).mean()
                    loss=policy_loss+value_loss+.25*offset_loss
                    metrics={'policy_ce':float(policy_loss.detach()),'value_loss':float(value_loss.detach()),'offset_loss':float(offset_loss.detach())}
                if not torch.isfinite(loss):raise RuntimeError('Nonfinite RVQ training loss')
                optimizer.zero_grad(set_to_none=True);loss.backward();grad=torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
                if not torch.isfinite(grad):raise RuntimeError('Nonfinite RVQ gradient')
                optimizer.step();progress['updates']+=1;seen+=len(rows);loss_sum+=float(loss.detach())*len(rows)
                monitor.emit(progress['updates'],'supervised_'+stage,{'train':{**metrics,'gradient_norm':float(grad),'epoch':epoch+1}})
                if progress['updates']%100==0:print('RVQ_UPDATE:',stage,progress['updates'],metrics,flush=True)
            if not seen:return
            validation=evaluate(model,data,stage,device,weights,batch_size)
            paused=(root/'pause.flag').exists();progress['epoch']=epoch if paused else epoch+1
            # A partial epoch must not advance early-stopping patience.
            improved=validation['score']<progress['best_score']-1e-4
            if improved:progress['best_score']=validation['score'];progress['stale_epochs']=0
            elif not paused:progress['stale_epochs']+=1
            change=float(torch.sqrt(sum(((p.detach()-initial[n])**2).sum() for n,p in model.named_parameters() if n in initial)))
            if not change>0:raise RuntimeError('No trainable RVQ weights changed')
            save(latest,checkpoint());atomic_json(folder/'progress.json',progress)
            if improved:
                save(folder/'best.pt',checkpoint());atomic_json(folder/'selected.json',{
                    'sha256':sha256(folder/'best.pt'),'validation':validation,'epoch':progress['epoch'],'updates':progress['updates']})
            report={'epoch':epoch+1,'updates':progress['updates'],'validation':validation,'train_loss':loss_sum/seen,
                'parameter_change_l2':change,'paused_mid_epoch':paused,'seconds':time.perf_counter()-start,
                'rl_updates':0,'self_play_games':0}
            atomic_json(folder/f'epoch_{epoch+1:04d}.json',report)
            monitor.emit(progress['updates'],'validation',{'validation':validation,'learning':{'parameter_change_l2':change}})
            print('RVQ_EPOCH:',stage,report,flush=True)
            if paused:return
    finally:monitor.close()


def train(dataset,root,*,codec_epochs=15,policy_epochs=15,device='auto',batch_size=64,wandb_mode='online',config=None):
    root=Path(root).resolve();dataset=Path(dataset).resolve()
    if not root.is_relative_to(ROOT/'data/isolated'):raise ValueError('RVQ run must stay under project data/isolated')
    if not 1<=codec_epochs<=200 or not 1<=policy_epochs<=200 or not 4<=batch_size<=256:raise ValueError('Invalid RVQ training budget')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested device is unavailable')
    if wandb_mode not in ('online','offline','disabled'):raise ValueError('Invalid W&B mode')
    config=config or {'codec':{'latent':128,'hidden':512,'levels':4,'codes':64},'policy':{'context':256,'hidden':1024}}
    protocol={'schema':'replay-rvq-training-v1','dataset_sha256':sha256(dataset/'manifest.json'),'code':source_identity(),
        'config':config,'batch_size':batch_size,'seed':20261022,'learning':'offline_human_replay_imitation',
        'codec_lr':2e-4,'policy_lr':1e-4,'codec_frozen_for_policy':True,'rl_updates':0,'self_play_games':0,
        'runtime':{name:version(name) for name in ('torch','numpy','rlgym','rlgym-rocket-league','rlgym-tools','rocketsim')}}
    root.mkdir(parents=True,exist_ok=True)
    with process_lock(root/'train.lock'):
        old=read_json(root/'protocol.json')
        if old is not None and old!=protocol:raise ValueError('RVQ code/dataset/settings changed; preserve this run and choose a new name')
        if old is None:atomic_json(root/'protocol.json',protocol)
        (root/'pause.flag').unlink(missing_ok=True)
        torch.set_num_threads(2);torch.manual_seed(20261022);random.seed(20261022);np.random.seed(20261022)
        if device=='cuda':torch.cuda.manual_seed_all(20261022)
        data=RVQData(dataset,root/'labels');sample=sample_controls(data.raw)
        weights=torch.as_tensor(positive_weights(sample),device=device)
        atomic_json(root/'training_control_sample.json',{'split':'train','sampled_chunks':len(sample),
            'positive_weights':weights.cpu().tolist(),'held_tick_fractions':(sample[:,:,5:]>.5).mean((0,1)).tolist(),
            'seed':20261022,'note':'Training-only sampled prevalence; not a count of independent matches.'})
        atomic_json(root/'model.json',{'config':config,'input':'current_state_only','levels':4,'codes_per_level':64,
            'initialization':'fresh_random; codec learned on training-split human chunks only','pretrained_external_weights':False})
        print('RVQ_DATA:',dataset,'| samples',data.raw.sample_count,'| device',device,'| original cache unchanged',flush=True)
        if (root/'policy/latest.pt').exists():
            progress=read_json(root/'codec/progress.json')
            if progress['epoch']<codec_epochs and progress['stale_epochs']<4:raise ValueError('Codec is frozen after policy creation; use a new run to extend codec training')
        else:stage_train(root,data,'codec',epochs=codec_epochs,device=device,weights=weights,settings={
            'mode':wandb_mode,'project':'slater-replay-rvq','entity':''},config=config,batch_size=batch_size)
        if (root/'pause.flag').exists():print('RVQ_PAUSED: completed checkpoints are saved',flush=True);return root
        info=read_json(root/'codec/selected.json');path=root/'codec/best.pt'
        if info['sha256']!=sha256(path):raise ValueError('Selected codec changed')
        if info.get('updates',0)==0:raise ValueError('Codec did not improve over initialization. Inspect codec reports before policy training.')
        if max(info['validation']['codes_used'])<2:raise ValueError('Codec collapsed to one action. Inspect reports; policy training was not started.')
        codec=ActionCodec(**config['codec']);codec.load_state_dict(torch.load(path,map_location='cpu',weights_only=True)['model']);codec.to(device).eval()
        calibration=calibrate_codec(root,data,codec,weights,device,batch_size)
        codec_digest=hashlib.sha256((info['sha256']+':'+calibration).encode()).hexdigest()
        data.use_codec(codec,codec_digest,device)
        stage_train(root,data,'policy',epochs=policy_epochs,device=device,weights=weights,settings={
            'mode':wandb_mode,'project':'slater-replay-rvq','entity':''},config=config,batch_size=batch_size,lr=1e-4,
            codec=codec,codec_digest=codec_digest)
        atomic_json(root/'status.json',{'codec':read_json(root/'codec/progress.json'),'policy':read_json(root/'policy/progress.json'),
            'paused':(root/'pause.flag').exists(),'selected_policy':str(root/'policy/best.pt'),'competitive_strength_verified':False})
        return root
