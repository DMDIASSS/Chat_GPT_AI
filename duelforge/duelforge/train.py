"""Fixed-horizon PPO. Frozen opponent rows never enter the learner loss.
C++ handles simulation/observations/rewards; tensor math uses PyTorch/LibTorch.
"""
import copy,json,math,os,random,signal,time
from pathlib import Path
import numpy as np
import torch
from torch.distributions import Categorical
from .runtime import ROOT,config,validate,batch,device,save,load,atomic_json,source_hashes,actor_sha,lock,sha,CONTRACT
from .model import ActorCritic
from .learning import entropy_coefficient,bootstrap_parts,evaluation_summary
from .execution import make_optimizer,configure_optimizer,checked_step


def gae(rewards,values,next_value,terminated,truncated,timeout_values,gamma,lam):
    if rewards.shape!=values.shape or terminated.shape!=values.shape or truncated.shape!=values.shape:raise ValueError('GAE row shapes differ')
    advantage=np.zeros_like(rewards);carry=np.zeros_like(next_value)
    for t in reversed(range(len(rewards))):
        nv=next_value if t==len(rewards)-1 else values[t+1]
        nv=np.where(truncated[t],timeout_values[t],nv)
        delta=rewards[t]+gamma*(~terminated[t])*nv-values[t]
        carry=delta+gamma*lam*(~(terminated[t]|truncated[t]))*carry;advantage[t]=carry
    return advantage,advantage+values


def tracker(cfg,folder,run_id):
    if cfg.get('acquisition') or os.environ.get('DUELFORGE_WANDB_EXTERNAL')=='1':
        print('WANDB_EXTERNAL: local metrics only in trainer; separate uploader handles network.',flush=True)
        return None
    if not cfg.get('wandb',{}).get('enabled'):return None
    try:
        import wandb
        available=bool(os.environ.get('WANDB_API_KEY')) or (Path.home()/'.netrc').is_file() or (Path.home()/'_netrc').is_file()
        return wandb.init(project=cfg['wandb']['project'],name=folder.name,id=run_id,resume='allow' if run_id else None,config=cfg,dir=str(folder.resolve()),mode=os.environ.get('WANDB_MODE','online' if available else 'offline'),settings=wandb.Settings(init_timeout=15))
    except Exception as ex:print('WANDB_UNAVAILABLE:',type(ex).__name__,'; local reporting continues.',flush=True);return None


def rss_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss/2**20
    except ImportError:
        if os.name!='nt':
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        try:
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in ('peakWorking','working','quotaPeakPaged','quotaPaged','quotaPeakNonPaged','quotaNonPaged','pagefile','peakPagefile','private')]
            c=Counters();c.cb=ctypes.sizeof(c)
            ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
            api=ctypes.windll.psapi.GetProcessMemoryInfo;api.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];api.restype=wintypes.BOOL
            if not api(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),c.cb):return None
            return c.working/2**20
        except Exception:return None


def train(folder,cfg=None,minutes=60,max_updates=None,stop_at_transitions=None,external_stop_file=None):
    folder=Path(folder)
    if minutes is not None and not 0<minutes<=90:raise ValueError('Prototype training sessions are bounded to 0..90 minutes; resume later for more')
    with lock(folder):return _train(folder,cfg,minutes,max_updates,stop_at_transitions,external_stop_file)


def _train(folder,cfg,minutes,max_updates,stop_at_transitions=None,external_stop_file=None):
    checkpoint=folder/'latest.pt';previous=None
    if checkpoint.is_file():
        previous=load(checkpoint);saved_cfg=previous['config']
        if cfg is not None and cfg!=saved_cfg:raise ValueError('Existing run config differs; create a new run instead of silently changing it')
        cfg=saved_cfg
    else:cfg=copy.deepcopy(cfg or config())
    validate(cfg);torch.set_num_threads(cfg['torch_threads']);dev=device(cfg);random.seed(cfg['seed']);np.random.seed(cfg['seed']);torch.manual_seed(cfg['seed'])
    model=ActorCritic(cfg['width']).to(dev);optimizer,opt_name=make_optimizer(model,cfg,dev)
    count=updates=physics=arena_decisions=player_decisions=consumed=0;history=[];run_id=None;prior_wall=0.;session_index=0
    if previous:
        model.load_state_dict(previous['model']);optimizer.load_state_dict(previous['optimizer']);configure_optimizer(optimizer,dev,opt_name)
        count=previous['learning_transitions'];updates=previous['updates'];physics=previous['physics_ticks'];arena_decisions=previous['arena_decisions'];player_decisions=previous['player_decisions'];consumed=previous['optimizer_examples'];history=previous['history'];run_id=previous.get('wandb_id');prior_wall=previous['training_wall_seconds'];session_index=previous.get('sessions',0)
        random.setstate(previous['python_rng']);np.random.set_state(previous['numpy_rng']);torch.set_rng_state(previous['torch_rng'].cpu())
        if dev.type=='cuda' and previous.get('cuda_rng') is not None:torch.cuda.set_rng_state_all([x.cpu() for x in previous['cuda_rng']])
    else:
        atomic_json(folder/'config.json',cfg);atomic_json(folder/'provenance.json',{'initialization':'fresh random model; no old project weights or tutor','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_hashes':source_hashes(),'contract':CONTRACT,'seed':cfg['seed'],'resume_contract':'Model/Adam/RNG/counters resume. Simulator episodes restart and that event is recorded.'})
    # Script the MLP without replacing parameter objects held by Adam.
    if cfg.get('execution','torchscript')=='torchscript':
        compiled=torch.jit.script(model)
        if any(p is not q for p,q in zip(model.parameters(),compiled.parameters())):raise RuntimeError('Scripted parameters detached from optimizer')
        model=compiled
    seed=(cfg['seed']+session_index*104729)%(0x40000000);session_index+=1
    env=batch(cfg,seed=seed)
    if cfg.get('held_ball'):
        from .held_ball import HeldBallBatch
        env=HeldBallBatch(env,cfg,seed)
        if previous and previous.get('held_curriculum'):env.restore_curriculum(previous['held_curriculum'])
    elif cfg.get('acquisition'):
        from .acquisition import AcquisitionBatch
        if cfg.get('air_recovery'):
            from .air_recovery import AirBatch
            env=AirBatch(env,cfg,seed)
        else:env=AcquisitionBatch(env,cfg,seed)
    raw=env.observe();E=cfg['n_envs'];T=cfg['ppo']['steps'];p=cfg['ppo'];locations=env.pad_locations()
    folder.joinpath('STOP').unlink(missing_ok=True);stopping=False
    def stop_requested():return (folder/'STOP').exists() or (external_stop_file is not None and Path(external_stop_file).exists())
    def stop(*_):
        nonlocal stopping
        stopping=True;(folder/'STOP').write_text('interrupt requested\n');print('PAUSE_REQUESTED: finishing the fixed rollout/update and saving.',flush=True)
    prior_signal=signal.signal(signal.SIGINT,stop)
    from . import _native
    atomic_json(folder/f'session_{time.time_ns()}.json',{'session':session_index,'native_seed':seed,'starting_learning_transitions':count,'starting_updates':updates,'episodes_restarted':True,'native_sha256':sha(_native.__file__),'source_hashes':source_hashes(),'torch':torch.__version__,'device':str(dev),'optimizer':opt_name,'execution':cfg.get('execution','torchscript')})
    wb=tracker(cfg,folder,run_id);run_id=wb.id if wb else run_id
    atomic_json(folder/'wandb_status.json',{'id':run_id,'url':getattr(wb,'url',None),'active':wb is not None,'local':'metrics.jsonl'})
    start=time.perf_counter();last_save=start;session_updates=0;eval_bucket=count//cfg['auto_evaluate_every'];last_snapshot=count//cfg['league']['snapshot_every']
    def checkpoint_payload():
        return {'format':'duelforge-checkpoint-v1','contract':CONTRACT,'config':cfg,'model':model.state_dict(),'optimizer':optimizer.state_dict(),'learning_transitions':count,'updates':updates,'physics_ticks':physics,'arena_decisions':arena_decisions,'player_decisions':player_decisions,'optimizer_examples':consumed,'training_wall_seconds':prior_wall+time.perf_counter()-start,'history':history,'wandb_id':run_id,'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if dev.type=='cuda' else None,'sessions':session_index,'held_curriculum':env.curriculum_state() if cfg.get('held_ball') else None}
    def persist():save(checkpoint,checkpoint_payload())
    persist()
    if not (folder/'initial.pt').is_file():
        import shutil
        shutil.copy2(checkpoint,folder/'initial.pt');atomic_json(folder/'initial_identity.json',{'sha256':sha(folder/'initial.pt'),'actor_state_sha256':actor_sha(model.state_dict()),'learning_transitions':0})
    # Each arena keeps its opponent until reset; snapshots are frozen in memory.
    nexto=None
    if cfg['league'].get('nexto_fraction',0)>0:
        from .nexto import Nexto
        nexto=Nexto()
    opponent=[None]*E;side=np.zeros(E,np.int64);frozen={};retired=set()
    def frozen_model(name):
        if name not in frozen:
            data=load(folder/'history'/name,dev)
            with torch.random.fork_rng(devices=[]):m=ActorCritic(cfg['width']).to(dev).eval()
            m.load_state_dict(data['model']);frozen[name]=torch.jit.script(m.actor)
        return frozen[name]
    def assign(indices):
        pool=history[-cfg['league']['max_history']:]
        for i in indices:
            r=np.random.random();nf=cfg['league'].get('nexto_fraction',0)
            opponent[i]='nexto' if nexto is not None and r<nf else str(np.random.choice(pool)) if pool and r<nf+cfg['league']['history_fraction'] else None
            side[i]=np.random.randint(2)
            if opponent[i] not in (None,'nexto'):frozen_model(opponent[i])
        active={x for x in opponent if x is not None};keep=set(pool)|active
        for name in list(frozen):
            if name not in keep:del frozen[name]
        for name in list(retired):
            if name not in active:(folder/'history'/name).unlink(missing_ok=True);retired.remove(name)
    assign(range(E))
    shape=(T,E,2);obs=np.empty((*shape,109),np.float32);masks=np.empty((*shape,90),bool);actions=np.empty(shape,np.int64);logp=np.empty(shape,np.float32);values=np.empty(shape,np.float32);rewards=np.empty(shape,np.float32);terminal=np.empty(shape,bool);truncated=np.empty(shape,bool);timeouts=np.zeros(shape,np.float32);learner=np.ones(shape,bool);entropy_weights=np.empty(shape,np.float32)
    error=False
    print(f'TRAINING: {dev}; {E} native arenas; {sum(x.numel() for x in model.parameters()):,} parameters; Octane 1v1; 120Hz physics / 15Hz decisions; session limit {minutes} minutes. Ctrl+C or 2_PAUSE.bat saves.',flush=True)
    try:
        while not stopping and not stop_requested():
            if max_updates is not None and session_updates>=max_updates:break
            if stop_at_transitions is not None and count>=stop_at_transitions:break
            if minutes is not None and time.perf_counter()-start>=minutes*60:break
            held_counts={k:0 for k in ('completed_held','successful_held','completed_released','successful_released','elevated_contacts')};t0=time.perf_counter();parts=np.zeros((2,3),np.float64);touches=np.zeros(2,np.int64);goals=np.zeros(2,np.int64);timeouts_pending=[];episode_resets=0;history_rows=0;behavior=np.zeros(5,np.float64);control_stats=np.zeros(3,np.float64);bootstrap_sum=np.zeros((2,2),np.float64);entropy_coef=entropy_coefficient(cfg,count);model.eval()
            for t in range(T):
                obs[t]=raw['obs'];masks[t]=raw['mask'];learner[t]=True
                entropy_weights[t]=env.entropy_coefficients() if cfg.get('held_ball') else entropy_coef
                with torch.inference_mode():
                    x=torch.as_tensor(raw['obs'].reshape(-1,109),device=dev);legal=torch.as_tensor(raw['mask'].reshape(-1,90),device=dev);logits,v=model(x,legal)
                    probs=logits.softmax(-1);a=torch.multinomial(probs,1).squeeze(1);lp=logits.log_softmax(-1).gather(1,a[:,None]).squeeze(1)
                    packed=torch.stack([a.float(),lp,v],-1).cpu().numpy().reshape(E,2,3)
                    actions[t]=packed[:,:,0];logp[t]=packed[:,:,1];values[t]=packed[:,:,2]
                    for name in {x for x in opponent if x is not None}:
                        ix=np.array([i for i in range(E) if opponent[i]==name]);cols=side[ix];learner[t,ix,cols]=False
                        if name=='nexto':
                            sub={k:raw[k][ix] for k in ('world','pads')}
                            actions[t,ix,cols]=nexto.act(sub,locations,cols);continue
                        hx=torch.as_tensor(raw['obs'][ix,cols],device=dev);hm=torch.as_tensor(raw['mask'][ix,cols],device=dev);hl=frozen_model(name)(hx).masked_fill(~hm,-1e9)
                        actions[t,ix,cols]=torch.multinomial(hl.softmax(-1),1).squeeze(1).cpu().numpy()
                if cfg.get('held_ball'):env.learning_rows=learner[t]
                before=raw;raw=env.step(actions[t]);extra=bootstrap_parts(cfg,before,raw,count);bootstrap_sum+=extra.sum(0);rewards[t]=raw['rewards']+extra.sum(-1);control_stats+=evaluation_summary(cfg,raw['final_world'],actions[t]);terminal[t]=raw['terminated'][:,None];truncated[t]=raw['truncated'][:,None];timeouts[t]=0
                ix=np.flatnonzero(raw['truncated'])
                if len(ix):timeouts_pending.append((t,ix,raw['final_obs'][ix].reshape(-1,109),raw['final_mask'][ix].reshape(-1,90)))
                parts+=raw['reward_parts'].sum(0);touches+=raw['info'][:,1:3].sum(0).astype(np.int64);g=raw['info'][:,0];goals+=[np.count_nonzero(g>0),np.count_nonzero(g<0)];physics+=int(raw['info'][:,3].sum());arena_decisions+=E;player_decisions+=E*2
                cars=raw['final_world'][:,1:];distance=np.linalg.norm(cars[:,:,:3]-raw['final_world'][:,0:1,:3],axis=-1).mean();speed=np.linalg.norm(cars[:,:,3:6],axis=-1).mean();back=(np.sum(cars[:,:,3:6]*cars[:,:,9:12],-1)<-300).mean();air=(cars[:,:,16]<.5).mean();jump=(actions[t]>=24).mean();behavior+=[distance,speed,back,air,jump]
                done=np.flatnonzero(raw['terminated']|raw['truncated']);episode_resets+=len(done);assign(done)
                if cfg.get('held_ball'):
                    for key in held_counts:held_counts[key]+=env.last[key]
                if stop_requested():stopping=True
            # Actor weights stayed fixed. Value all timeouts before any optimizer step.
            x=np.concatenate([raw['obs'].reshape(-1,109)]+[item[2] for item in timeouts_pending]);lm=np.concatenate([raw['mask'].reshape(-1,90)]+[item[3] for item in timeouts_pending]);vs=[]
            with torch.inference_mode():
                for k in range(0,len(x),p['batch_size']):vs.append(model(torch.as_tensor(x[k:k+p['batch_size']],device=dev),torch.as_tensor(lm[k:k+p['batch_size']],device=dev))[1].cpu().numpy())
            vs=np.concatenate(vs);next_value=vs[:E*2].reshape(E,2);offset=E*2
            for t,ix,x,l in timeouts_pending:size=len(ix)*2;timeouts[t,ix]=vs[offset:offset+size].reshape(len(ix),2);offset+=size
            adv,returns=gae(rewards,values,next_value,terminal,truncated,timeouts,p['gamma'],p['gae_lambda']);index=np.flatnonzero(learner.reshape(-1));samples=len(index)
            if samples==0:raise RuntimeError('No learner rows; refusing empty PPO update')
            flat_adv=adv.reshape(-1);av=flat_adv[index];flat_adv[index]=(av-av.mean())/(av.std()+1e-8)
            collect=time.perf_counter()-t0;arrays=[obs.reshape(-1,109),masks.reshape(-1,90),actions.reshape(-1),logp.reshape(-1),flat_adv,returns.reshape(-1),entropy_weights.reshape(-1)]
            cache=dev.type=='cuda' and sum(a.nbytes for a in arrays)/2**20<=cfg['rollout_cache_mb'];data=[torch.as_tensor(a,device=dev if cache else 'cpu') for a in arrays];opt_start=time.perf_counter();stats=[];early=False;model.train()
            for epoch in range(p['epochs']):
                np.random.shuffle(index)
                for k in range(0,len(index),p['batch_size']):
                    idx=torch.as_tensor(index[k:k+p['batch_size']],device=dev if cache else 'cpu');x,l,a,old,ad,ret,entropy_weight=[v.index_select(0,idx).to(dev,non_blocking=True) for v in data]
                    logits,v=model(x,l);d=Categorical(logits=logits,validate_args=False);delta=d.log_prob(a)-old;ratio=delta.exp();kl=((ratio-1)-delta).mean();entropy_per_row=d.entropy();entropy=entropy_per_row.mean()
                    policy=-torch.minimum(ratio*ad,ratio.clamp(1-p['clip'],1+p['clip'])*ad).mean();value=.5*(v-ret).square().mean();loss=policy+p['value']*value-(entropy_weight*entropy_per_row).mean()
                    okay,norm=checked_step(loss,kl,model,optimizer,p['max_grad_norm'],p['target_kl'])
                    if not okay:early=True;break
                    consumed+=len(idx);stats.append(torch.stack([loss.detach(),kl.detach(),entropy.detach(),norm]).cpu().numpy())
                if early:break
            if not torch.stack([torch.isfinite(v).all() for v in model.parameters()]).all().item():raise FloatingPointError('Nonfinite parameters; last checkpoint preserved')
            optimize=time.perf_counter()-opt_start;elapsed=time.perf_counter()-t0;count+=samples;updates+=1;session_updates+=1
            if count//cfg['league']['snapshot_every']>last_snapshot:
                (folder/'history').mkdir(exist_ok=True);name=f'{count:016d}.pt';save(folder/'history'/name,{'model':model.state_dict(),'config':cfg,'learning_transitions':count});history.append(name);last_snapshot=count//cfg['league']['snapshot_every']
                while len(history)>cfg['league']['max_history']:retired.add(history.pop(0))
            mean=np.mean(stats,axis=0) if stats else np.zeros(4);memory=rss_mb();gpu_alloc=torch.cuda.max_memory_allocated(dev)/2**20 if dev.type=='cuda' else 0;gpu_res=torch.cuda.memory_reserved(dev)/2**20 if dev.type=='cuda' else 0
            legal_max=float(np.log(np.maximum(1,masks.reshape(-1,90)[index].sum(-1))).mean());normalized_entropy=float(mean[2])/max(legal_max,1e-6)
            metric={'train/entropy_coefficient':entropy_coef,'train/legal_entropy_max_nats':legal_max,'train/entropy_fraction_of_legal_max':normalized_entropy,'game/reverse_throttle_fraction':float(control_stats[0]/T),'game/jump_button_fraction':float(control_stats[1]/T),'game/forward_drive_fraction':float(control_stats[2]/T),'reward/bootstrap/approach':float(bootstrap_sum[:,0].sum()),'reward/bootstrap/new_contact':float(bootstrap_sum[:,1].sum()),'state':'training','update':updates,'learning_transitions':count,'optimizer_examples':consumed,'training_wall_seconds':prior_wall+time.perf_counter()-start,'speed/learner_transitions_per_second':samples/elapsed,'speed/rollout_player_decisions_per_second':T*E*2/collect,'speed/collection_seconds':collect,'speed/ppo_seconds':optimize,'train/loss':float(mean[0]),'train/KL':float(mean[1]),'train/entropy_nats':float(mean[2]),'train/gradient_norm':float(mean[3]),'train/optimizer_minibatches':len(stats),'train/KL_early_stop':early,'game/touches_blue':int(touches[0]),'game/touches_orange':int(touches[1]),'game/goals_blue':int(goals[0]),'game/goals_orange':int(goals[1]),'game/resets':episode_resets,'game/ball_distance_mean':float(behavior[0]/T),'game/car_speed_mean':float(behavior[1]/T),'game/backward_fraction':float(behavior[2]/T),'game/airborne_fraction':float(behavior[3]/T),'game/aerial_table_action_fraction':float(behavior[4]/T),'league/history_size':len(history),'league/frozen_rows':int((~learner).sum()),'resource/trainer_rss_mb':memory,'resource/cuda_allocated_peak_mb':gpu_alloc,'resource/cuda_reserved_mb':gpu_res,'execution':cfg.get('execution','torchscript'),'optimizer':opt_name,'device':str(dev),'physics_ticks':physics,'arena_decisions':arena_decisions,'player_decisions':player_decisions,'rollout_cache_gpu':cache}
            if cfg.get('held_ball'):
                metric.update({'held/'+key:value for key,value in held_counts.items()})
                for task in ('held','released'):
                    metric['held/'+task+'_contact_fraction']=held_counts['successful_'+task]/max(1,held_counts['completed_'+task])
                metric['train/entropy_base_coefficient']=entropy_coef
                metric['train/entropy_coefficient']=float(entropy_weights.reshape(-1)[index].mean())
                metric['train/drill_entropy_coefficient']=cfg['held_ball']['drill_entropy']
            if cfg.get('acquisition'):
                metric.update({'acquisition/'+k:v for k,v in env.last.items()})
                from .acquisition import adapt_learning_rate
                metric['train/learning_rate_used']=optimizer.param_groups[0]['lr']
                metric['train/learning_rate_next']=adapt_learning_rate(optimizer,cfg,max(float(mean[1]),p['target_kl']*1.5) if early else float(mean[1]))
            if cfg.get('predictive',{}).get('enabled'):
                metric.update({'predictive/'+key:value for key,value in env.reward.last.items()});metric['speed/reward_seconds_per_call']=env.reward_seconds/max(1,env.reward_calls)
            for a in (0,1):
                for j,name in enumerate((('goal','mixed_task_shaping' if (cfg.get('air_recovery') or cfg.get('held_ball')) else 'contact_approach' if cfg['acquisition']['stage']=='contact' else 'possession','first_contact') if cfg.get('acquisition') else ('goal','potential','impulse'))):metric[f'reward/{"blue" if a==0 else "orange"}/{name}']=float(parts[a,j])
            with (folder/'metrics.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(metric,allow_nan=False)+'\n')
            atomic_json(folder/'status.json',metric)
            if wb:
                try:wb.log({k:v for k,v in metric.items() if isinstance(v,(int,float,bool))},step=count)
                except Exception as ex:print('WANDB_LOG_UNAVAILABLE:',type(ex).__name__,flush=True);wb=None
            print(f'UPDATE {updates}: {count:,} learner transitions | {samples/elapsed:,.0f}/s end-to-end | touches {int(touches.sum())} goals {int(goals.sum())} | KL {float(mean[1]):.4f} | collect {collect:.2f}s / PPO {optimize:.2f}s | entropy {float(mean[2]):.2f}/{legal_max:.2f}, coef {metric["train/entropy_coefficient"]:.4f} | {dev}',flush=True)
            if gpu_alloc>cfg['max_cuda_allocated_mb'] or gpu_res>cfg['max_cuda_reserved_mb'] or (memory is not None and memory>cfg['max_trainer_rss_mb']):
                print('RESOURCE_GUARD_PAUSE: configured memory target exceeded; saving completed update.',flush=True);stopping=True
            if time.perf_counter()-last_save>=cfg['checkpoint_every_seconds']:persist();last_save=time.perf_counter()
            if count//cfg['auto_evaluate_every']>eval_bucket and not stopping:
                persist();eval_bucket=count//cfg['auto_evaluate_every']
                from .evaluate import evaluate
                result=evaluate(folder,games_per_context=cfg['auto_eval_games_per_context'],seconds=cfg['auto_eval_seconds'],automatic=True)
                if wb:
                    try:wb.log({'eval/score_rate_vs_initial':result['overall']['score_rate'],'eval/open_play_score':result['contexts']['open_play']['score_rate']},step=count)
                    except Exception:pass
                if (cfg.get('predictive',{}).get('enabled') or cfg.get('acquisition')) and result['overall']['score_interval_95'][1]<.45:
                    print('PARENT_REGRESSION_PAUSE: validation upper score bound below 45%; experiment saved, trained parent preserved.',flush=True);stopping=True
                model.train()
    except BaseException:
        error=True;raise
    finally:
        if not error:persist()
        signal.signal(signal.SIGINT,prior_signal)
        atomic_json(folder/'status.json',{'state':'error' if error else 'paused','learning_transitions':count,'updates':updates,'checkpoint':str(checkpoint),'training_wall_seconds':prior_wall+time.perf_counter()-start,'last_checkpoint_preserved_after_error':error})
        if wb:
            try:wb.finish()
            except Exception:pass
        print('TRAINING_ERROR_LAST_CHECKPOINT_PRESERVED:' if error else 'PAUSED_AND_SAVED:',checkpoint,flush=True)
    return count
