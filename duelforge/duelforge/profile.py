"""Bounded per-stage profile; no existing runs are resumed or reconfigured."""
import copy,json,time,tempfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,config,device,batch,atomic_json
from .model import ActorCritic

def select_arenas(result,default=64):
    rows=result.get('full_training',[]);valid=[v for v in rows if v.get('measured_updates',0)>=3 and v['median_learner_transitions_s']>0]
    base=next((v for v in valid if v['arenas']==default),None)
    if not base or not valid:return default
    best=max(valid,key=lambda v:v['median_learner_transitions_s'])
    return int(best['arenas']) if best['median_learner_transitions_s']>=1.10*base['median_learner_transitions_s'] else default

def profile(seconds=2.,full=True,cfg=None):
    if not .1<=seconds<=5:raise ValueError('Use 0.1..5 seconds per case')
    cfg=copy.deepcopy(cfg or config());dev=device(cfg);torch.set_num_threads(cfg['torch_threads']);rows=[]
    for n in (32,64,128,256):
        env=batch(cfg,n=n);raw=env.observe();ac=np.full((n,2),16,np.int64)
        net=torch.jit.script(ActorCritic(cfg['width']).to(dev).eval())
        for _ in range(20):env.step(ac)
        t=time.perf_counter();calls=0
        while time.perf_counter()-t<seconds:env.step(ac);calls+=1
        row={'arenas':n,'native_physics_features_rewards_player_decisions_s':calls*n*2/(time.perf_counter()-t)}
        obs=torch.as_tensor(raw['obs'].reshape(-1,109),device=dev);legal=torch.as_tensor(raw['mask'].reshape(-1,90),device=dev)
        with torch.inference_mode():
            for _ in range(20):net(obs,legal)
            if dev.type=='cuda':torch.cuda.synchronize()
            t=time.perf_counter();calls=0
            while time.perf_counter()-t<seconds:
                net(obs,legal)
                if dev.type=='cuda':torch.cuda.synchronize()
                calls+=1
            row['inference_only_player_decisions_s']=calls*n*2/(time.perf_counter()-t)
            t=time.perf_counter();calls=0
            while time.perf_counter()-t<seconds:
                logits,_=net(torch.as_tensor(raw['obs'].reshape(-1,109),device=dev),torch.as_tensor(raw['mask'].reshape(-1,90),device=dev));raw=env.step(logits.argmax(-1).cpu().numpy().reshape(n,2));calls+=1
            row['combined_collection_player_decisions_s']=calls*n*2/(time.perf_counter()-t)
        rows.append(row);print('STAGE_PROFILE:',json.dumps(row),flush=True)
    result={'device':str(dev),'gpu':torch.cuda.get_device_name() if dev.type=='cuda' else None,'stages':rows,'scope':'Separate scopes. Physics rates include observations/masks/rewards. Combined collection includes transfers. Full PPO rate below uses distinct scratch runs.'}
    if full:
        from .train import train
        folder=ROOT/'benchmarks'/('profile_'+str(time.time_ns()));full_rows=[]
        for n in (64,128,256):
            c=copy.deepcopy(cfg);c['n_envs']=n;c['ppo']['steps']=16384//n;c['wandb']['enabled']=False;c['auto_evaluate_every']=10**12;c['league']['snapshot_every']=10**12
            run=folder/str(n);train(run,c,minutes=1,max_updates=3);
            if (run/'STOP').exists():raise KeyboardInterrupt('Profiling stopped; real training has not started')
            metrics=[json.loads(v) for v in (run/'metrics.jsonl').read_text().splitlines()];full_rows.append({'arenas':n,'rollout_steps':c['ppo']['steps'],'measured_updates':len(metrics),'median_learner_transitions_s':float(np.median([v['speed/learner_transitions_per_second'] for v in (metrics[1:] or metrics)])),'scratch_run':str(run.relative_to(ROOT))})
        result['full_training']=full_rows
    result['config_changed']=False;atomic_json(ROOT/'results/stage_profile.json',result);print('PROFILE_SAVED:',ROOT/'results/stage_profile.json',flush=True);return result
