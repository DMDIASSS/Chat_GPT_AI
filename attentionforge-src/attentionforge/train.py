import contextlib,copy,json,os,random,time,signal,sys,math
from pathlib import Path
import numpy as np
import torch
from torch.distributions import Categorical
from .model import ActorCritic
from .performance import sample_actions,RolloutStore
from .execution import make_optimizer,configure_optimizer,select_model_execution,compile_checked,checked_step
from .observation import encode
from .runtime import ROOT,atomic_json,save_checkpoint,source_hashes,batch,device

def gae(rewards,values,next_value,terminated,truncated,timeout_values,gamma,lam):
    advantages=np.zeros_like(rewards);carry=np.zeros_like(next_value)
    for t in reversed(range(len(rewards))):
        done=terminated[t]|truncated[t]
        vn=next_value if t==len(rewards)-1 else values[t+1]
        vn=np.where(truncated[t],timeout_values[t],vn)
        delta=rewards[t]+gamma*(~terminated[t])*vn-values[t]
        carry=delta+gamma*lam*(~done)*carry;advantages[t]=carry
    return advantages,advantages+values

@contextlib.contextmanager
def lock_run(folder):
    folder.mkdir(parents=True,exist_ok=True);f=(folder/'trainer.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            f.seek(0);f.write(b'0');f.flush();f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('A trainer already owns this run. Use PAUSE first.')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('A trainer already owns this run. Use PAUSE first.')
        yield
    finally:f.close()

def load(path,dev):
    # Only load your own checkpoints; a full optimizer/RNG checkpoint is Python pickle.
    return torch.load(path,map_location=dev,weights_only=False)

def tracker(cfg,folder,existing_id=None):
    if not cfg.get('wandb',{}).get('enabled',False):return None
    try:
        import wandb
        # The SDK uses an existing environment key or netrc login. Never print/read key contents.
        settings=wandb.Settings(init_timeout=15)
        authenticated=bool(os.environ.get('WANDB_API_KEY')) or (Path.home()/'.netrc').exists() or (Path.home()/'_netrc').exists()
        mode=os.environ.get('WANDB_MODE','online' if authenticated else 'offline')
        return wandb.init(project=cfg['wandb']['project'],name=folder.name,id=existing_id,resume='allow' if existing_id else None,config=cfg,dir=str(folder.resolve()),mode=mode,settings=settings)
    except Exception as ex:
        print('WANDB_UNAVAILABLE:',type(ex).__name__,'; local metrics continue.',flush=True);return None

def train(cfg,folder,max_updates=None,minutes=None):
    folder=Path(folder)
    with lock_run(folder):return _train(cfg,folder,max_updates,minutes)

def _train(cfg,folder,max_updates,minutes):
    ck=folder/'latest.pt';stop=folder/'STOP';stop.unlink(missing_ok=True)
    torch.set_num_threads(int(cfg['torch_threads']));dev=device(cfg)
    random.seed(cfg['seed']);np.random.seed(cfg['seed']);torch.manual_seed(cfg['seed'])
    model=ActorCritic(**cfg['network']).to(dev);opt,optimizer_name=make_optimizer(model,cfg,dev)
    count=update=0;history=[];history_scores={};wbid=None;previous_wall=0;previous_physics=previous_env=0;recovery_attempts=0
    if ck.exists():
        saved=load(ck,dev);recovery_attempts=saved.get('recovery_attempts',0)
        if saved['config']!=cfg:raise ValueError('This run has a different saved config. Use a new run name for config changes.')
        model.load_state_dict(saved['model']);opt.load_state_dict(saved['optimizer']);configure_optimizer(opt,dev,optimizer_name);count=saved['learning_transitions'];update=saved['updates'];history=saved['history'];history_scores=saved.get('history_scores',{});wbid=saved.get('wandb_id');previous_wall=saved.get('training_wall_seconds',0);previous_physics=saved.get('physics_ticks',0);previous_env=saved.get('env_decisions',0)
        random.setstate(saved['python_rng']);np.random.set_state(saved['numpy_rng']);torch.set_rng_state(saved['torch_rng'].cpu())
        if dev.type=='cuda' and saved.get('cuda_rng') is not None:torch.cuda.set_rng_state_all([s.cpu() for s in saved['cuda_rng']])
        print('RESUME:',count,'learning transitions. Episodes restart; optimizer and model resume.',flush=True)
    else:
        atomic_json(folder/'config.json',cfg);atomic_json(folder/'provenance.json',{'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_hashes':source_hashes(),'initialization':'random','native_contract':'attentionforge-v1-raw32-delay1','hitbox':'Octane','physics_hz':120,'decision_hz':120/cfg['tick_skip']})
    model,model_execution,execution_probes=select_model_execution(model,cfg,dev)
    atomic_json(folder/'execution_profile.json',{'model_execution':model_execution,'optimizer':optimizer_name,'probes':execution_probes})
    print('EXECUTION:',model_execution,optimizer_name,'FP32; existing weights/optimizer state preserved.',flush=True)
    from . import _attention_native
    from .runtime import sha
    native_seed=(cfg['seed']+update*104729) % (0x40000000 if cfg.get('attack') or cfg.get('library') else (1<<32))
    atomic_json(folder/f'session_{time.time_ns()}.json',{'execution_version':'attentionforge-gpu-v3','model_execution':model_execution,'optimizer':optimizer_name,'starting_learning_transitions':count,'starting_update':update,'native_seed':native_seed,'source_hashes':source_hashes(),'native_module_sha256':sha(_attention_native.__file__),'torch':torch.__version__,'device':str(dev)})
    env=batch(cfg,seed=native_seed);locations=env.pad_locations();raw=env.observe();obs,legal=encode(raw['world'],raw['pads'],locations)
    wb=tracker(cfg,folder,wbid);wbid=wb.id if wb else wbid
    atomic_json(folder/'wandb_status.json',{'available':wb is not None,'id':wbid,'url':getattr(wb,'url',None) if wb else None,'local_metrics':'metrics.jsonl'})
    rehearsal=None
    if cfg.get('attack'):
        from .movement_school import load_rehearsal
        rehearsal=load_rehearsal(cfg,folder)
        if not (folder/'best_contact.json').exists():
            from .skills import drills
            initial_contact=drills(model,cfg,n=16,seed=880001)
            initial_score=min(v[k] for v in initial_contact.values() for k in ('blue_contact_fraction','orange_contact_fraction'))
            atomic_json(folder/'best_contact.json',{'minimum_contact_fraction':initial_score,'learning_transitions':count,'quality':initial_contact,'source':'Unmodified parent actor, before offense updates'})
        if not (folder/'offense_initial_probe.json').exists():
            from .offense import skill_probes
            initial_probe=skill_probes(model,cfg,n=16);initial_probe['learning_transitions']=count;atomic_json(folder/'offense_initial_probe.json',initial_probe);print('OFFENSE_BASELINE_PROBES:',initial_probe,flush=True)
    p=cfg['ppo'];steps=int(p['steps']);e=cfg['n_envs'];a=cfg['team_size']*2;shape=(steps,e,a)
    # Host buffers: no multi-hundred-MB rollout allocation in a 4GB GPU.
    ob=np.empty((*shape,43,40),np.float32);lm=np.empty((*shape,90),bool)
    actions=np.empty(shape,np.int64);logs=np.empty(shape,np.float32);vals=np.empty(shape,np.float32);rewards=np.empty(shape,np.float32)
    term=np.empty(shape,bool);trunc=np.empty(shape,bool);tv=np.zeros(shape,np.float32)
    frozen=ActorCritic(**cfg['network']).to(dev).eval()
    if model_execution=='torchscript':frozen=compile_checked(frozen)
    start=time.perf_counter();last_save=start;session_updates=0;session_physics=session_env=0;last_snapshot=count//cfg['league']['snapshot_every'];stopping=False
    def request_stop(*_):
        nonlocal stopping
        stopping=True;print('PAUSE_REQUESTED: finishing the current rollout/update, then saving.',flush=True)
    previous_handler=signal.signal(signal.SIGINT,request_stop)
    def save():
        save_checkpoint(ck,{'format':'attentionforge-checkpoint-v1','config':cfg,'model':model.state_dict(),'optimizer':opt.state_dict(),'learning_transitions':count,'updates':update,'history':history,'history_scores':history_scores,'wandb_id':wbid,'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all() if dev.type=='cuda' else None,'training_wall_seconds':previous_wall+time.perf_counter()-start,'physics_ticks':previous_physics+session_physics,'env_decisions':previous_env+session_env,'recovery_attempts':recovery_attempts})
    save();print(f'TRAINING: {dev}, {e} arenas, {a} cars, {sum(p.numel() for p in model.parameters()):,}-parameter attention, Octane, {120/cfg["tick_skip"]:g}Hz decisions. Ctrl+C requests a save after this rollout/update.',flush=True)
    training_failed=False
    try:
        while not stopping and not stop.exists():
            if max_updates is not None and session_updates>=max_updates:break
            if minutes is not None and time.perf_counter()-start>=minutes*60:break
            t0=time.perf_counter()
            if dev.type=='cuda':torch.cuda.reset_peak_memory_stats(dev)
            behavior=np.zeros(4,np.float64);selected=None;histmask=np.zeros((e,a),bool)
            if history:
                weights=np.array([(1-history_scores.get(name,0.5))**2+0.05 for name in history]);weights/=weights.sum();selected=np.random.choice(history,p=weights)
                frozen.load_state_dict(load(folder/'history'/selected,dev)['model'])
                nh=max(1,int(e*cfg['league']['history_env_fraction']))
                for j in range(nh):histmask[j,(j%2)*cfg['team_size']:((j%2)+1)*cfg['team_size']]=True
            trainmask=~histmask;stats=np.zeros(8,np.float64);extra_stats=np.zeros(10,np.float64);control_abs=possession_abs=0.;h_w=h_d=h_l=0;timeout_states=[]
            histidx=torch.as_tensor(np.flatnonzero(histmask.ravel()),device=dev,dtype=torch.long)
            model.eval()
            library_stats=np.zeros((2,5),np.float64)
            skill_stats=np.zeros(6,np.float64);attack_stats=np.zeros(9,np.float64);backward_count=0.
            if cfg.get('skills'):
                fraction=.6 if count<3000000 else .35 if count<10000000 else .15
                env.drill_fraction(fraction);env.skill_stage(min(1.,count/10000000))
            for t in range(steps):
                ob[t]=obs;lm[t]=legal
                with torch.no_grad():
                    ot=torch.as_tensor(obs.reshape(-1,43,40),device=dev);lt=torch.as_tensor(legal.reshape(-1,90),device=dev)
                    logits,v=model(ot,lt);ac,lp=sample_actions(logits)
                    if selected:
                        hlogits,_=frozen(ot.index_select(0,histidx),lt.index_select(0,histidx));ha,_=sample_actions(hlogits);ac.index_copy_(0,histidx,ha)
                    packed=torch.stack((ac.float(),lp,v),dim=-1).cpu().numpy().reshape(e,a,3)
                    actions[t]=packed[:,:,0];logs[t]=packed[:,:,1];vals[t]=packed[:,:,2]
                raw=env.step(actions[t]);rewards[t]=raw['rewards'];term[t]=raw['terminated'][:,None];trunc[t]=raw['truncated'][:,None];tv[t]=0
                if np.any(raw['truncated']):
                    ix=np.flatnonzero(raw['truncated']);fo,fl=encode(raw['final_world'][ix],raw['final_pads'][ix],locations)
                    timeout_states.append((t,ix,fo.reshape(-1,43,40),fl.reshape(-1,90)))
                obs,legal=encode(raw['world'],raw['pads'],locations);stats+=raw['info'].sum(axis=0)
                if 'library_info' in raw:library_stats+=raw['library_info'].sum(axis=0)
                if 'skill_info' in raw:skill_stats+=raw['skill_info'].sum(axis=0)
                if cfg.get('attack'):
                    attack_stats+=raw['attack_info'][:,:9].sum(axis=0)
                if 'reward_info' in raw:
                    extra_stats+=raw['reward_info'].sum(axis=0)
                    control_abs+=np.abs(raw['reward_info'][:,0]).sum();possession_abs+=np.abs(raw['reward_info'][:,1]).sum()
                cars=raw['world'][:,1:]
                if cfg.get('attack'):backward_count+=np.mean(np.sum(cars[:,:,3:6]*cars[:,:,9:12],axis=-1)<-300)
                behavior+=np.array([np.linalg.norm(cars[:,:,:3]-raw['world'][:,0:1,:3],axis=-1).mean(),np.linalg.norm(cars[:,:,3:6],axis=-1).mean(),(cars[:,:,16]<0.5).mean(),(actions[t]>=24).mean()])
                if selected:
                    for j in range(nh):
                        g=raw['info'][j,0]
                        if g:
                            learner_sign=1 if histmask[j,cfg['team_size']] else -1
                            if g*learner_sign>0:h_w+=1
                            else:h_l+=1
                if t%64==0 and (stopping or stop.exists()):
                    # Complete the fixed rollout for PPO; never optimize uninitialized rows.
                    stopping=True
            # All rollout weights remain fixed: timeouts can be evaluated together.
            vx=np.concatenate([obs.reshape(-1,43,40)]+[x[2] for x in timeout_states],axis=0)
            vm=np.concatenate([legal.reshape(-1,90)]+[x[3] for x in timeout_states],axis=0)
            predictions=[]
            with torch.no_grad():
                for b in range(0,len(vx),p['batch_size']):
                    predictions.append(model(torch.as_tensor(vx[b:b+p['batch_size']],device=dev),torch.as_tensor(vm[b:b+p['batch_size']],device=dev))[1].cpu().numpy())
            predictions=np.concatenate(predictions);next_v=predictions[:e*a].reshape(e,a);offset=e*a
            for t,ix,fo,fl in timeout_states:
                size=len(ix)*a;tv[t,ix]=predictions[offset:offset+size].reshape(len(ix),a);offset+=size
            adv,returns=gae(rewards,vals,next_v,term,trunc,tv,p['gamma'],p['gae_lambda'])
            flat=np.flatnonzero(np.broadcast_to(trainmask,shape).reshape(-1));new_samples=len(flat);rollout_sec=time.perf_counter()-t0
            af=adv.reshape(-1)[flat];advflat=adv.reshape(-1);advflat[flat]=(af-af.mean())/(af.std()+1e-8)
            loss_metrics=[];model.train();early=False
            optimize_start=time.perf_counter()
            store=RolloutStore([ob.reshape(-1,43,40),lm.reshape(-1,90),actions.reshape(-1),logs.reshape(-1),advflat,returns.reshape(-1)],dev,cfg.get('performance',{}).get('rollout_cache_mb',512))
            for epoch in range(p['epochs']):
                np.random.shuffle(flat)
                permutation=store.permutation(flat)
                for s in range(0,len(flat),p['batch_size']):
                    idx=permutation[s:s+p['batch_size']]
                    x,l,ac,old,ad,ret=store.get(idx)
                    logits,v=model(x,l);dist=Categorical(logits=logits,validate_args=False)
                    diff=dist.log_prob(ac)-old;ratio=diff.exp();kl=((ratio-1)-diff).mean()
                    policy=-torch.minimum(ad*ratio,ad*ratio.clamp(1-p['clip'],1+p['clip'])).mean();vl=0.5*(v-ret).square().mean();entropy=dist.entropy().mean();loss=policy+p['value']*vl-p['entropy']*entropy
                    if cfg.get('skills') and not cfg.get('attack'):
                        from .skills import tutor
                        eligible=(x[:,0,16]>.5)&(x[:,1,26]*2044<180)
                        weight=cfg['skills']['auxiliary_initial']*max(0.,1-count/cfg['skills']['auxiliary_decay_transitions'])
                        aux=-dist.log_prob(tutor(x,l))
                        loss=loss+weight*(aux*eligible).sum()/eligible.sum().clamp_min(1)
                    if rehearsal is not None:
                        elapsed_phase=count-cfg['attack']['start_learning_transitions']
                        settings=cfg['attack'].get('rehearsal',{})
                        coefficient=settings.get('weight',.02)*max(0.,1-elapsed_phase/settings.get('decay_new_transitions',5000000))
                        if coefficient>0:
                            rx,rl,ry=rehearsal;ri=np.random.randint(0,len(ry),32)
                            rlogits,_=model(torch.as_tensor(rx[ri],device=dev),torch.as_tensor(rl[ri],device=dev))
                            loss=loss+coefficient*torch.nn.functional.cross_entropy(rlogits,torch.as_tensor(ry[ri],device=dev))
                    accepted,grad_norm=checked_step(loss,kl,model,opt,p['max_grad_norm'],p['target_kl'])
                    if not accepted:early=True;break
                    loss_metrics.append(torch.stack((loss.detach(),kl.detach(),entropy.detach(),((ratio.detach()-1).abs()>p['clip']).float().mean())))
                if early:break
            cache_used=store.cached;del store
            summary=torch.stack(loss_metrics).mean(0).cpu().numpy() if loss_metrics else np.zeros(4)
            optimize_sec=time.perf_counter()-optimize_start
            count+=new_samples;update+=1;session_updates+=1;session_env+=steps*e;session_physics+=int(stats[7])
            if selected and h_w+h_l:
                score=h_w/(h_w+h_l);history_scores[selected]=0.8*history_scores.get(selected,0.5)+0.2*score
            if count//cfg['league']['snapshot_every']>last_snapshot:
                name=f'{count:016d}.pt';(folder/'history').mkdir(exist_ok=True);save_checkpoint(folder/'history'/name,{'model':model.state_dict(),'config':cfg,'learning_transitions':count});history.append(name);last_snapshot=count//cfg['league']['snapshot_every']
                if not (folder/'baseline.pt').exists():
                    import shutil
                    shutil.copyfile(folder/'history'/name,folder/'baseline.pt')
                while len(history)>cfg['league']['max_history']:
                    old=history.pop(0);(folder/'history'/old).unlink(missing_ok=True);history_scores.pop(old,None)
            elapsed=time.perf_counter()-t0;wall=previous_wall+time.perf_counter()-start
            metrics={'update':update,'learning_transitions':count,'env_decisions':previous_env+session_env,'physics_ticks':previous_physics+session_physics,'training_wall_seconds':wall,'speed/rollout_player_decisions_per_second':steps*e*a/rollout_sec,'speed/learning_transitions_per_second':new_samples/elapsed,'speed/update_wall_seconds':elapsed,'speed/collection_seconds':rollout_sec,'speed/ppo_seconds':optimize_sec,'performance/gpu_rollout_cache':cache_used,'performance/model_execution':model_execution,'performance/torchscript':model_execution=='torchscript','performance/optimizer':optimizer_name,'performance/adam_fused':optimizer_name=='adam_fused','performance/gpu_peak_mb':torch.cuda.max_memory_allocated(dev)/1024**2 if dev.type=='cuda' else 0.,'train/loss':float(summary[0]),'train/approx_kl':float(summary[1]),'train/entropy':float(summary[2]),'train/clip_fraction':float(summary[3]),'train/kl_early_stop':early,'train/optimizer_minibatches':len(loss_metrics),'game/goals':int(np.count_nonzero(term))/a,'game/mean_ball_distance':float(behavior[0]/steps),'game/mean_car_speed':float(behavior[1]/steps),'game/airborne_fraction':float(behavior[2]/steps),'game/air_action_fraction':float(behavior[3]/steps),'game/touches_blue':int(stats[1]),'game/touches_orange':int(stats[2]),'reward/goal_blue_sum':float(stats[3]),('reward/approach_blue_sum' if cfg['rewards'].get('profile') in ('rlgym_simple_v1','control_shots_v1','skills_v1','attack_v1','rlgym_tools_v1') else 'reward/potential_blue_sum'):float(stats[4]),'reward/touch_blue_sum':float(stats[5]),'reward/control_blue_sum':float(stats[6]),'league/history_size':len(history),'league/opponent':selected,'device':str(dev),'state':'training'}
            if cfg['rewards'].get('profile')=='control_shots_v1':
                metrics.update({'control/blue_score_mean':float(extra_stats[0]/(e*steps)),'control/absolute_score_mean':float(control_abs/(e*steps)),'control/floor_tracking_enabled':cfg['rewards'].get('goal_no_floor',0)>0,'reward/possession_absolute_mean':float(possession_abs/(e*steps)),'reward/possession_blue_sum':float(extra_stats[1]),'reward/no_floor_goal_blue_sum':float(extra_stats[2]),'reward/goal_speed_blue_sum':float(extra_stats[3]),'game/no_floor_goals':int(extra_stats[4]),'game/goal_speed_mean':float(extra_stats[5]/metrics['game/goals']) if metrics['game/goals'] else 0.,'game/credited_shot_goals':int(extra_stats[6]),'game/shot_floor_contact_detections':int(extra_stats[7])})
            if cfg.get('skills'):
                metrics.update(dict(zip(('skills/contact_events','skills/touch_strength_sum','skills/air_touch_events','skills/reset_events','skills/goal_combo_bonus_sum','skills/shot_touch_sum'),map(float,skill_stats))))
                metrics['skills/drill_fraction']=fraction
                metrics['skills/effective_touch_weight']=1-.8*min(1.,count/10000000)
                metrics['skills/effective_approach_rate']=1-.6*min(1.,count/10000000)
            if cfg.get('attack'):
                metrics.update(dict(zip(('attack/aim_improvement_reward','attack/useful_launch_reward','attack/useful_flip_reward','attack/backflip_recovery_reward','attack/jump_contact_reward','attack/air_approach_reward','attack/on_target_touches','attack/kickoff_scene_goals','attack/open_scene_goals'),map(float,attack_stats))))
                metrics['attack/new_transitions']=count-cfg['attack']['start_learning_transitions']
                metrics['attack/backward_fraction']=float(backward_count/steps)
                metrics['attack/rehearsal_weight']=.02*max(0.,1-(count-cfg['attack']['start_learning_transitions'])/5000000) if rehearsal is not None else 0.
                metrics['skills/drill_fraction']=.7
                metrics['skills/effective_touch_weight']=.1;metrics['skills/effective_approach_rate']=.3
            if cfg.get('library'):
                from .library_rewards import NAMES
                for color in (0,1):
                    for k,name in enumerate(NAMES):metrics['reward_library/'+('blue' if color==0 else 'orange')+'/'+name]=float(library_stats[color,k])
                metrics['library/new_transitions']=count-cfg['library']['start_learning_transitions']
            with (folder/'metrics.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(metrics,allow_nan=False)+'\n')
            atomic_json(folder/'status.json',metrics)
            if wb:
                try:wb.log({k:v for k,v in metrics.items() if isinstance(v,(float,int,bool))},step=count)
                except Exception as ex:
                    print('WANDB_LOG_UNAVAILABLE:',type(ex).__name__,'; local metrics continue.',flush=True);wb=None
            cache_label='GPU' if cache_used else 'host'
            print(f'UPDATE {update}: {count:,} learning transitions | {new_samples/elapsed:,.0f}/s end-to-end | touches {int(stats[1]+stats[2])}, goals {int(np.count_nonzero(term)/a)} | KL {metrics["train/approx_kl"]:.4f} | collect {rollout_sec:.1f}s / PPO {optimize_sec:.1f}s | cache {cache_label}',flush=True)
            if time.perf_counter()-last_save>=cfg['checkpoint_every_seconds']:save();last_save=time.perf_counter()
            if cfg.get('library'):
                period=cfg['library']['validation_every'];offset=cfg['library']['start_learning_transitions']
                if (count-offset)//period>(count-new_samples-offset)//period:
                    save()
                    from .library import monitor as library_monitor
                    if not library_monitor(model,cfg,folder,count):stopping=True
            period=cfg['attack']['validation_every'] if cfg.get('attack') else cfg.get('skills',{}).get('auto_evaluate_every',1)
            offset=cfg.get('attack',{}).get('start_learning_transitions',0)
            if cfg.get('skills') and (count-offset)//period>(count-new_samples-offset)//period:
                save()
                from .offense import monitor as attack_monitor
                from .skills import monitor as contact_monitor
                monitor=attack_monitor if cfg.get('attack') else contact_monitor
                if not monitor(model,cfg,folder,count):
                    print('VALIDATION_STOP: saved latest; parent and retained checkpoints preserved. See validation reports.',flush=True);stopping=True
    except BaseException:
        training_failed=True
        raise
    finally:
        if not training_failed:save()
        signal.signal(signal.SIGINT,previous_handler)
        atomic_json(folder/'status.json',{'state':'error' if training_failed else 'paused','learning_transitions':count,'updates':update,'checkpoint':str(ck),'training_wall_seconds':previous_wall+time.perf_counter()-start,'checkpoint_preserved_after_error':training_failed})
        if wb:
            try:wb.finish()
            except Exception as ex:print('WANDB_FINISH_UNAVAILABLE:',type(ex).__name__,flush=True)
        print('TRAINING_FAILED_LAST_CHECKPOINT_PRESERVED:' if training_failed else 'PAUSED_AND_SAVED:',ck,flush=True)
