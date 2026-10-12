"""Isolated hybrid replay/RocketSim trainer. Measured candidates, not endless promises."""
from __future__ import annotations
import argparse
import copy
from importlib.metadata import version
import json
from pathlib import Path
import random
import shutil
import time
import numpy as np
import torch
from torch.nn import functional as F
from slater_mechanics_env import collect_batched
from slater_mechanics_eval import load_actor
from slater_versatile_data import DemoDataset,prepare
from slater_versatile_env import VersatileEnv,VersatileCritic,TASKS
from slater_versatile_eval import evaluate,skill_guard,EvaluationPaused
from slater_ppo import trust_region_update
from slater_v041_core import sha256,atomic_json,read_json,process_lock
from slater_v041_overnight import write_checkpoint
import slater_cycle9_native_ppo_v025 as base

ROOT=Path(__file__).resolve().parent
DEFAULT={
 'n_envs':8,'steps_per_env':256,'updates_per_cycle':20,'max_cycles':12,'plateau_cycles':3,
 'actor_lr':1e-5,'critic_lr':1e-4,'epochs':2,'minibatch':256,'target_kl':.015,
 'teacher_anchor':.03,'bc_lr':2e-6,'bc_every':4,'bc_batches':2,'bc_max_kl':.01,
 'episode_seconds':12,'screen_seeds':2,'screen_seconds':30,
 'confirm_seeds':12,'confirm_seconds':60,'family_alpha':.05,'seed':20261012,
 'opponents':{},'tasks':{'match':.20,'ground':.15,'defense':.15,'recovery':.06,'low_boost':.08,
 'aerial':.08,'wall':.05,'air_dribble':.05,'air_finish':.025,'reset_use':.025,'replay':.06,'teamplay':.07}}

Paused=EvaluationPaused

def validate(cfg):
    for key,(low,high) in {'n_envs':(2,16),'steps_per_env':(32,2048),'updates_per_cycle':(1,1000),
        'max_cycles':(1,100),'plateau_cycles':(1,100),'epochs':(1,8),'minibatch':(16,4096),
        'bc_every':(1,1000),'bc_batches':(0,8),'screen_seeds':(1,4),'screen_seconds':(8,90),
        'confirm_seeds':(8,64),'confirm_seconds':(30,300)}.items():
        if type(cfg[key]) is not int or not low<=cfg[key]<=high:raise ValueError('Invalid '+key)
    for key,(low,high) in {'actor_lr':(1e-7,5e-5),'critic_lr':(1e-6,.001),'bc_lr':(1e-7,1e-5),
        'target_kl':(.001,.05),'bc_max_kl':(.001,.05),'teacher_anchor':(0,.3),
        'episode_seconds':(3,30),'family_alpha':(.001,.1)}.items():
        if not np.isfinite(cfg[key]) or not low<=cfg[key]<=high:raise ValueError('Invalid '+key)
    if cfg['minibatch']>cfg['n_envs']*cfg['steps_per_env']:raise ValueError('Minibatch exceeds rollout')
    if not cfg['tasks'] or any(k not in TASKS or not np.isfinite(v) or v<=0 for k,v in cfg['tasks'].items()):raise ValueError('Invalid task mixture')
    if type(cfg['seed']) is not int or not 1<=cfg['seed']<100000000:raise ValueError('Invalid seed')
    if cfg['confirm_seeds']<np.ceil(np.log2(2*cfg['max_cycles']/cfg['family_alpha'])):
        raise ValueError('Confirmation seed budget too small for the configured multiple-comparison limit')
    return cfg


def bc_update(actor,optimizer,data,rng,*,size,lr,max_kl):
    batch=data.batch(rng,size);x=tuple(torch.from_numpy(batch[k]) for k in ('q','kv','mask'))
    target=torch.from_numpy(batch['target']);weight=torch.from_numpy(batch['weight'])
    with torch.no_grad():old=base.logits_of(actor,x).log_softmax(-1);old_prob=old.exp()
    weights={k:v.detach().clone() for k,v in actor.state_dict().items()};opt=copy.deepcopy(optimizer.state_dict())
    try:
        for attempt in range(4):
            actor.load_state_dict(weights);optimizer.load_state_dict(copy.deepcopy(opt))
            for group in optimizer.param_groups:group['lr']=lr*.5**attempt
            logp=base.logits_of(actor,x).log_softmax(-1)
            ce=(-(target*logp).sum(-1)*weight).sum()/weight.sum()
            loss=ce+.1*(old_prob*(old-logp)).sum(-1).mean()
            if not torch.isfinite(loss):raise FloatingPointError('Nonfinite replay loss')
            optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(actor.parameters(),.5);optimizer.step()
            with torch.no_grad():
                post=base.logits_of(actor,x).log_softmax(-1)
                kl=float((old_prob*(old-post)).sum(-1).mean())
            if np.isfinite(kl) and kl<=max_kl:
                return {'accepted':True,'ce':float(ce.detach()),'batch_policy_kl':max(0.,kl),'backtracks':attempt}
        actor.load_state_dict(weights);optimizer.load_state_dict(opt)
        return {'accepted':False,'batch_policy_kl':kl,'backtracks':3}
    except BaseException:
        actor.load_state_dict(weights);optimizer.load_state_dict(opt);raise


def validation_loss(actor,data,*,split='validation',limit=4096,batch_size=256):
    ids=data.indices[split]
    if len(ids)>limit:ids=ids[np.linspace(0,len(ids)-1,limit,dtype=int)]
    losses=[];counts=[]
    with torch.no_grad():
        for start in range(0,len(ids),batch_size):
            batch=data.take(ids[start:start+batch_size]);x=tuple(torch.from_numpy(batch[k]) for k in ('q','kv','mask'))
            logp=base.logits_of(actor,x).log_softmax(-1);target=torch.from_numpy(batch['target']);w=torch.from_numpy(batch['weight'])
            losses.append(float((-(target*logp).sum(-1)*w).sum()));counts.append(float(w.sum()))
    return sum(losses)/sum(counts)


def choose_tasks(cfg,cycle,dataset):
    tasks={k:v for k,v in cfg['tasks'].items() if k!='replay' or dataset is not None}
    names=list(tasks);weights=np.asarray(list(tasks.values()),float);weights/=weights.sum()
    rng=np.random.default_rng(cfg['seed']+cycle*7919)
    # Keep two normal-match worlds; remaining worlds rotate across the curriculum.
    return ['match','ground']+rng.choice(names,cfg['n_envs']-2,p=weights).tolist()


def code_identity():
    names=('slater_replicar.py','slater_versatile_trainer.py','slater_versatile_data.py','slater_versatile_env.py','slater_versatile_eval.py',
        'slater_mechanics_env.py','slater_mechanics_core.py','slater_mechanics_eval.py','slater_cycle9_native_ppo_v025.py',
        'slater_ppo.py','afk_team_research.py','nexto_teacher.py','slater_nexto_scheduler_v038b.py','mechanics_scenarios.py',
        'vendor/nexto/nexto_obs.py','slater_v041_worker.py','slater_v041_overnight.py','slater_v041_core.py','afk_replay_tas_learning.py')
    return {name:sha256(ROOT/name) for name in names}


def run_path(name):
    if not name or len(name)>50 or not name.replace('_','').replace('-','').isalnum():raise ValueError('Use a short run name with letters/digits/_/-')
    return ROOT/'data/isolated/versatile'/name


def train(name,source=None,dataset_path=None,*,resume=False,cycles=3,config=None):
    run=run_path(name)
    if not resume and run.exists():raise FileExistsError('Run exists: use resume or a new name')
    saved=read_json(run/'protocol.json') if resume else None
    if resume and not saved:raise ValueError('No saved versatile run')
    if saved:
        cfg=saved['config'];source=Path(saved['source']['path']);dataset_path=saved['dataset_path']
    else:cfg={**DEFAULT,**(config or {})}
    validate(cfg)
    source=Path(source).resolve();dataset=DemoDataset(dataset_path) if dataset_path else None
    paths={'nexto':ROOT/'vendor/nexto/nexto-model.pt','frozen_start':source}
    for key,path in cfg['opponents'].items():
        if key in paths:raise ValueError('Reserved opponent name '+key)
        paths[key]=(ROOT/path).resolve()
    protocol={'config':cfg,'source':{'path':str(source),'sha256':sha256(source)},
        'opponents':{k:{'path':str(v),'sha256':sha256(v)} for k,v in paths.items()},
        'dataset_path':str(Path(dataset_path).resolve()) if dataset_path else None,
        'dataset_sha':sha256(Path(dataset_path)/'manifest.json') if dataset_path else None,
        'code':code_identity(),'runtime':{n:version(n) for n in ('torch','numpy','rlgym-rocket-league','rocketsim','rlgym-tools')}}
    if saved and saved!=protocol:raise ValueError('Source, dataset, code or settings changed; start a new run')
    run.mkdir(parents=True,exist_ok=True)
    with process_lock(run/'trainer.lock'):
        if not saved:atomic_json(run/'protocol.json',protocol)
        torch.set_num_threads(2);torch.manual_seed(cfg['seed']);random.seed(cfg['seed'])
        actor=load_actor(ROOT,source,trainable=True);critic=VersatileCritic()
        ao=torch.optim.Adam(actor.parameters(),lr=cfg['actor_lr']);co=torch.optim.Adam(critic.parameters(),lr=cfg['critic_lr'])
        state=read_json(run/'progress.json') if resume else {'updates':0,'cycle':0,'cycle_updates':0,'decisions':0,'phase':'training','plateau':0,'champion':str(source),'champion_sha':sha256(source),'history':[]}
        if resume:
            if state['protocol_sha']!=sha256(run/'protocol.json'):raise ValueError('Saved run protocol changed')
            if sha256(state['latest'])!=state['latest_sha']:raise ValueError('Resume checkpoint changed')
            doc=torch.load(state['latest'],map_location='cpu',weights_only=True)
            actor.load_state_dict(doc['actor']);critic.load_state_dict(doc['critic']);ao.load_state_dict(doc['actor_optimizer']);co.load_state_dict(doc['critic_optimizer'])
        else:
            state['protocol_sha']=sha256(run/'protocol.json')
            initial=run/'initial.pt'
            write_checkpoint(initial,{'actor':actor.state_dict(),'critic':critic.state_dict(),'actor_optimizer':ao.state_dict(),'critic_optimizer':co.state_dict()})
            state['champion']=str(initial);state['champion_sha']=sha256(initial)
            state['latest']=str(initial);state['latest_sha']=sha256(initial);atomic_json(run/'progress.json',state)
            atomic_json(run/'selected.json',{'checkpoint':str(initial),'sha256':state['champion_sha'],'status':'INITIAL_BASELINE','promotions':0})
        if sha256(state['champion'])!=state['champion_sha']:raise ValueError('Saved champion changed')
        if state['plateau']>=cfg['plateau_cycles']:
            print('VERSATILE_PLATEAU_STOP: no confirmed improvement. Inspect reports; start a revised run rather than repeating this protocol.',flush=True);return
        (run/'pause.flag').unlink(missing_ok=True) # resume/start are explicit requests to continue
        rivals={k:load_actor(ROOT,v) for k,v in paths.items()}
        teacher=load_actor(ROOT,Path(state['champion']))
        rng=np.random.default_rng(cfg['seed']+state['updates']*997)
        started=time.perf_counter();initial_decisions=state['decisions'];cycles_left=cycles
        def commit(filename):
            checkpoint=run/filename
            payload={'actor':actor.state_dict(),'critic':critic.state_dict(),'actor_optimizer':ao.state_dict(),
                'critic_optimizer':co.state_dict(),'global_updates':state['updates'],'stage':'slater_versatile',
                'meta':{'source_sha256':protocol['source']['sha256'],'dataset_sha':protocol['dataset_sha'],'cycle':state['cycle']}}
            write_checkpoint(checkpoint,payload)
            state['latest']=str(checkpoint);state['latest_sha']=sha256(checkpoint);atomic_json(run/'progress.json',state)
            return checkpoint
        while cycles_left and state['cycle']<cfg['max_cycles']:
            if (run/'pause.flag').exists():raise Paused()
            if state['phase']=='training':
                tasks=choose_tasks(cfg,state['cycle'],dataset)
                # Include a recent confirmed opponent without changing protected originals.
                training_rivals=dict(rivals)
                if state['history']:training_rivals['past_champion']=load_actor(ROOT,Path(state['history'][-1]['previous_champion']))
                envs=[VersatileEnv(training_rivals,task_name=t,dataset=dataset,max_seconds=cfg['episode_seconds']) for t in tasks]
                try:
                    seeds=[cfg['seed']+state['updates']*100003+j*7919 for j in range(len(envs))]
                    obs=[e.reset(s) for e,s in zip(envs,seeds)]
                    while state['cycle_updates']<cfg['updates_per_cycle']:
                        if (run/'pause.flag').exists():raise Paused()
                        if shutil.disk_usage(run).free<500*1024*1024:raise RuntimeError('Less than 500 MiB free: pause and free disk space')
                        step_started=time.perf_counter();before=sum(e.total_script_ticks for e in envs)
                        rows,episodes,obs,seeds,trunc=collect_batched(actor,critic,envs,obs,seeds,cfg['steps_per_env'])
                        collection=time.perf_counter()-step_started
                        for group in ao.param_groups:group['lr']=cfg['actor_lr']
                        metrics=trust_region_update(actor,teacher,critic,ao,co,rows,cfg['epochs'],cfg['minibatch'],
                            cfg['teacher_anchor'],cfg['seed']+state['updates'],target_kl=cfg['target_kl'])
                        bc=[]
                        if dataset and (state['updates']+1)%cfg['bc_every']==0:
                            for _ in range(cfg['bc_batches']):bc.append(bc_update(actor,ao,dataset,rng,size=cfg['minibatch'],lr=cfg['bc_lr'],max_kl=cfg['bc_max_kl']))
                        state['updates']+=1;state['cycle_updates']+=1;state['decisions']+=len(rows['action'])
                        checkpoint=commit(f"update_{state['updates']:06d}.pt")
                        metrics.update(update=state['updates'],cycle=state['cycle']+1,tasks=tasks,replay_bc=bc,
                            decisions=state['decisions'],collection_decisions_per_second=len(rows['action'])/max(collection,1e-9),
                            session_decisions_per_second=(state['decisions']-initial_decisions)/max(time.perf_counter()-started,1e-9),
                            scripted_rival_ticks=sum(e.total_script_ticks for e in envs)-before,timeout_bootstraps=trunc,
                            episode_outcomes=[{'task':e['task_name'],'outcome':e['outcome'],'success':e['success']} for e in episodes])
                        atomic_json(checkpoint.with_suffix('.json'),metrics)
                        print('VERSATILE_UPDATE',json.dumps(metrics,sort_keys=True),flush=True)
                finally:
                    for e in envs:e.close()
                state['candidate']=state['latest'];state['candidate_sha']=state['latest_sha'];state['phase']='screen';atomic_json(run/'progress.json',state)
            if (run/'pause.flag').exists():raise Paused()
            candidate=load_actor(ROOT,Path(state['candidate']));reference=load_actor(ROOT,Path(state['champion']))
            identity={'candidate_sha':state['candidate_sha'],'reference_sha':state['champion_sha'],
                      'rivals':protocol['opponents'],'code':protocol['code'],'runtime':protocol['runtime']}
            cycle=state['cycle']+1;folder=run/'evaluations'/f'{cycle:04d}'
            screen=evaluate(candidate,reference,rivals,out=folder/'screen.json',identity=identity,
                seeds=cfg['screen_seeds'],seconds=cfg['screen_seconds'],seed_base=cfg['seed']+cycle*1000000,pause_path=run/'pause.flag')
            confirmed=False;reason='screen_failed';holdout=None;guard=None
            if screen['verdict']['passed']:
                if (run/'pause.flag').exists():raise Paused()
                holdout=evaluate(candidate,reference,rivals,out=folder/'confirmation.json',identity=identity,
                    seeds=cfg['confirm_seeds'],seconds=cfg['confirm_seconds'],seed_base=cfg['seed']+cycle*1000000+100000,
                    alpha=cfg['family_alpha']/(2*cfg['max_cycles']),confirm=True,pause_path=run/'pause.flag')
                reason='confirmation_failed'
                if holdout['verdict']['passed']:
                    guard=skill_guard(candidate,reference,rivals,out=folder/'skills.json',identity=identity,
                        seed_base=cfg['seed']+cycle*1000000+200000,pause_path=run/'pause.flag')
                    confirmed=guard['passed'];reason='confirmed' if confirmed else 'skill_regression'
            report={'cycle':cycle,'candidate':state['candidate'],'champion_before':state['champion'],
                    'decision':reason,'confirmed':confirmed,'screen':screen['verdict'],
                    'confirmation':holdout['verdict'] if holdout else None,'skills':guard['guards'] if guard else None}
            if dataset:report['replay_validation_ce']=validation_loss(candidate,dataset)
            atomic_json(folder/'decision.json',report)
            if confirmed:
                state['history'].append({'cycle':cycle,'checkpoint':state['candidate'],'previous_champion':state['champion']})
                state['champion']=state['candidate'];state['champion_sha']=state['candidate_sha'];state['plateau']=0
                atomic_json(run/'selected.json',{'checkpoint':state['champion'],'sha256':state['champion_sha'],
                    'status':'CONFIRMED_SIMULATOR_CANDIDATE','promotions':len(state['history']),'evidence':str(folder/'decision.json')})
                teacher=load_actor(ROOT,Path(state['champion']))
            else:
                # Save each rejected candidate; restore all training state, not just actor weights.
                doc=torch.load(state['champion'],map_location='cpu',weights_only=True)
                actor.load_state_dict(doc['actor']);critic.load_state_dict(doc['critic']);ao.load_state_dict(doc['actor_optimizer']);co.load_state_dict(doc['critic_optimizer'])
                state['plateau']+=1
            state['cycle']+=1;state['cycle_updates']=0;state['phase']='training';cycles_left-=1
            commit(f"cycle_{cycle:04d}_resume.pt")
            print('VERSATILE_CYCLE',cycle,reason,'champion',state['champion'],'plateau',state['plateau'],flush=True)
            if state['plateau']>=cfg['plateau_cycles']:break
        for entry in [protocol['source'],*protocol['opponents'].values()]:
            if sha256(entry['path'])!=entry['sha256']:raise RuntimeError('Protected input changed')
        atomic_json(run/'session_summary.json',{'seconds':time.perf_counter()-started,'new_decisions':state['decisions']-initial_decisions,
            'cycle':state['cycle'],'updates':state['updates'],'champion':state['champion'],'plateau':state['plateau']})
        print('VERSATILE_STOPPED',run,'budget or plateau reached; source files untouched',flush=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','preflight','start','resume','status','pause','smoke'))
    p.add_argument('--source');p.add_argument('--dataset');p.add_argument('--run',default='versatile01')
    p.add_argument('--config');p.add_argument('--cycles',type=int,default=3)
    p.add_argument('--inputs',nargs='+',default=['data/replays']);p.add_argument('--out',default='data/isolated/versatile_data01')
    p.add_argument('--workers',type=int,default=2);p.add_argument('--max-replays',type=int,default=100)
    p.add_argument('--per-replay',type=int,default=1024);p.add_argument('--max-samples',type=int,default=100000)
    a=p.parse_args(argv)
    if not 1<=a.cycles<=100:p.error('cycles must be 1..100')
    if a.command=='prepare':
        prepare(a.inputs,ROOT/a.out,workers=a.workers,max_replays=a.max_replays,per_replay=a.per_replay,max_samples=a.max_samples);return
    if a.command=='status':print(json.dumps(read_json(run_path(a.run)/'progress.json',{}),indent=2));return
    if a.command=='pause':
        run=run_path(a.run)
        if not run.exists():raise ValueError('No run to pause')
        (run/'pause.flag').touch();print('Pause requested; completes current update/evaluation pair.');return
    if a.command=='resume':
        try:train(a.run,resume=True,cycles=a.cycles)
        except Paused:print('VERSATILE_PAUSED: checkpoints saved. Use resume to continue.')
        return
    if not a.source:p.error('--source is required: explicitly choose the checkpoint to continue')
    source=(ROOT/a.source).resolve();cfg={**DEFAULT,**read_json(ROOT/a.config,{})} if a.config else dict(DEFAULT)
    if a.command=='preflight':
        validate(cfg);load_actor(ROOT,source,trainable=True)
        paths=[ROOT/'vendor/nexto/nexto-model.pt',source]+[(ROOT/v).resolve() for v in cfg['opponents'].values()]
        for path in paths:load_actor(ROOT,path)
        if a.dataset:DemoDataset(ROOT/a.dataset)
        print('VERSATILE_PREFLIGHT_PASS CPU_NATIVE_ACTOR ALL_FROZEN_RIVALS_SCRIPTED',flush=True);return
    if a.command=='smoke':
        # Integration only, deliberately tiny and no promotion claims.
        cfg={**cfg,'n_envs':2,'steps_per_env':32,'epochs':1,'minibatch':32,'updates_per_cycle':1,
             'screen_seeds':1,'screen_seconds':8,'bc_every':1}
    try:train(a.run,source,ROOT/a.dataset if a.dataset else None,cycles=1 if a.command=='smoke' else a.cycles,config=cfg)
    except Paused:print('VERSATILE_PAUSED: checkpoints saved. Use resume to continue.')

if __name__=='__main__':main()
