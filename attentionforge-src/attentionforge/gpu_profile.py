"""Read-only model probes and a separate, provenance-preserving batch experiment."""
import copy,gc,json,math,os,shutil,tempfile,time
from pathlib import Path
import torch
from .runtime import ROOT,device,atomic_json,save_checkpoint,sha,source_hashes
from .train import load,lock_run
from .model import ActorCritic
from .execution import optimizer_probe,select_model_execution

def model_hash(state):
    import hashlib
    h=hashlib.sha256()
    for name,t in sorted(state.items()):
        h.update(name.encode());h.update(str(t.dtype).encode());h.update(str(tuple(t.shape)).encode());h.update(t.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()

def fork_checkpoint(source,target,saved,batch_size,execution,profile):
    source=Path(source);target=Path(target)
    if source.resolve()==target.resolve():raise ValueError('The experiment must have a separate run folder')
    if target.exists():raise FileExistsError(f'{target} already exists; it was not overwritten')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.gpu_fork_',dir=target.parent))
    try:
        payload=copy.deepcopy(saved);before=model_hash(payload['model']);cfg=payload['config']
        old_batch=cfg['ppo']['batch_size'];cfg['ppo']['batch_size']=int(batch_size)
        cfg.setdefault('performance',{})['model_execution']=execution
        payload['wandb_id']=None
        for name in payload.get('history',[]):
            if Path(name).name!=name:raise ValueError('Unexpected history checkpoint path')
            (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
        if (source/'baseline.pt').is_file():shutil.copy2(source/'baseline.pt',stage/'baseline.pt')
        save_checkpoint(stage/'latest.pt',payload);atomic_json(stage/'config.json',cfg)
        record={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_run':str(source.resolve()),'source_checkpoint_sha256':sha(source/'latest.pt'),'copied_model_state_sha256':before,'starting_learning_transitions':saved['learning_transitions'],'starting_updates':saved['updates'],'configuration_changes':{'ppo.batch_size':{'from':old_batch,'to':batch_size},'performance.model_execution':execution},'optimizer':'Moments and step values copied; execution flags normalized on resume.','wandb':'New run ID; parent run is preserved.','source_hashes':source_hashes()}
        assert model_hash(payload['model'])==before
        atomic_json(stage/'fork_provenance.json',record);atomic_json(stage/'provenance.json',{'initialization':'fork of trained checkpoint','parent':record})
        atomic_json(stage/'gpu_batch_profile.json',profile)
        # Atomic publish of the completed new directory. Never replace an existing run.
        if target.exists():raise FileExistsError(target)
        os.rename(stage,target);return record
    finally:
        if stage.exists():shutil.rmtree(stage)

def recent_phase(folder,cfg):
    p=Path(folder)/'metrics.jsonl';rows=[]
    if p.is_file():
        with p.open('rb') as f:
            f.seek(0,2);offset=max(0,f.tell()-131072);f.seek(offset);lines=f.read().splitlines()
        if offset:lines=lines[1:]
        for line in lines[-32:]:
            try:rows.append(json.loads(line))
            except (ValueError,UnicodeDecodeError):pass
    if rows:
        import statistics
        collection=statistics.median(x.get('speed/collection_seconds',cfg['n_envs']*cfg['team_size']*2*cfg['ppo']['steps']/max(1,x.get('speed/rollout_player_decisions_per_second',1))) for x in rows)
        samples=cfg['n_envs']*cfg['team_size']*2*cfg['ppo']['steps']
        if rows[-1].get('league/opponent'):
            nh=max(1,int(cfg['n_envs']*cfg['league']['history_env_fraction']));samples-=nh*cfg['team_size']*cfg['ppo']['steps']
        return float(collection),int(samples)
    return None,None

def profile_gpu(source,target=None):
    source=Path(source);target=Path(target or source.with_name(source.name+'_gpu'))
    if target.exists():raise FileExistsError(f'{target.name} already exists. Use GPU_RUN.bat to open it; the existing experiment was preserved.')
    if not (source/'latest.pt').is_file():raise FileNotFoundError(source/'latest.pt')
    with lock_run(source):
        saved=load(source/'latest.pt',torch.device('cpu'));cfg=saved['config'];dev=device(cfg)
        if dev.type!='cuda':raise RuntimeError('The GPU profiler requires a CUDA runtime. No checkpoint was changed.')
        torch.set_num_threads(cfg['torch_threads'])
        original_sha=sha(source/'latest.pt');model=ActorCritic(**cfg['network']).to(dev);model.load_state_dict(saved['model'])
        model,execution,model_probes=select_model_execution(model,cfg,dev)
        # Probe a plain model when optimizer_probe makes its own scripted copy.
        plain=ActorCritic(**cfg['network']).to(dev);plain.load_state_dict(saved['model']);del model;gc.collect();torch.cuda.empty_cache()
        collection,samples=recent_phase(source,cfg);rows=[]
        total_rows=cfg['n_envs']*cfg['team_size']*2*cfg['ppo']['steps'];cache_mb=min(cfg.get('performance',{}).get('rollout_cache_mb',512),total_rows*(43*40*4+90+24)/1024**2)
        free,_=torch.cuda.mem_get_info(dev);budget_mb=(free+torch.cuda.memory_allocated(dev))/1024**2*.85
        sizes=sorted(set([int(cfg['ppo']['batch_size']),256,512,1024]))
        print('GPU_BATCH_PROFILE: using disposable copies of the trained model; source weights and optimizer are preserved.',flush=True)
        for size in sizes:
            print('GPU_BATCH_PROBE:',size,execution,flush=True)
            try:
                row=optimizer_probe(plain,cfg,dev,size,scripted=execution=='torchscript')
                row['memory_budget_fit']=row['peak_probe_cuda_mb']+cache_mb<=budget_mb
                if collection is not None:
                    row['estimated_full_update_seconds']=collection+math.ceil(samples/size)*cfg['ppo']['epochs']*row['median_minibatch_seconds']
                    row['estimated_learning_transitions_per_second']=samples/row['estimated_full_update_seconds']
                rows.append(row)
                print('GPU_BATCH_RESULT:',size,round(row['optimizer_samples_per_second']),'optimizer samples/s; peak',round(row['peak_probe_cuda_mb']),'MiB; memory fit',row['memory_budget_fit'],flush=True)
            except torch.OutOfMemoryError:print('GPU_BATCH_SKIPPED:',size,'exceeded available memory',flush=True)
            finally:gc.collect();torch.cuda.empty_cache()
        choices=[x for x in rows if x['memory_budget_fit']]
        if not choices:raise RuntimeError('No probe fit the memory budget. Close GPU programs and retry; source was preserved.')
        key='estimated_learning_transitions_per_second' if collection is not None else 'optimizer_samples_per_second'
        fastest=max(x[key] for x in choices);winner=min((x for x in choices if x[key]>=fastest*.95),key=lambda x:x['batch_size'])
        profile={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'gpu':torch.cuda.get_device_name(dev),'torch':torch.__version__,'source_checkpoint_sha256':original_sha,'source_learning_transitions':saved['learning_transitions'],'model_execution':execution,'execution_probes':model_probes,'median_recent_collection_seconds':collection,'recent_learner_samples_per_update':samples,'probes':rows,'selected_batch_size':winner['batch_size'],'limitations':['Synthetic optimizer timing estimates throughput; actual full updates and held-out matches must confirm results.','A larger minibatch reduces optimizer steps per epoch and can change learning. It is a separate experiment.','Model, reward, tick skip, action delay, PPO epochs, learning rate and existing counters are preserved.']}
        assert sha(source/'latest.pt')==original_sha
        record=fork_checkpoint(source,target,saved,winner['batch_size'],execution,profile)
        atomic_json(source/'gpu_batch_profile.json',profile)
        print('GPU_EXPERIMENT_READY:',target,flush=True)
        print('PRESERVED_MODEL_HASH:',record['copied_model_state_sha256'],'; starting transitions:',saved['learning_transitions'],flush=True)
        print(f'Continue with: _RUN.bat laptop --run {target.name}',flush=True)
        if source.name=='laptop01':print('GPU_RUN.bat opens that new experiment; LAPTOP.bat keeps the original.',flush=True)
        return profile
