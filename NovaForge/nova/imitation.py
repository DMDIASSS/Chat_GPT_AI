"""Reward-weighted supervised copying of immutable teachers; no PPO updates."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime,timezone
import csv
import io
import json
import os
from pathlib import Path
import time
import tempfile
from types import SimpleNamespace
import uuid
import zipfile

import numpy as np
import torch
from filelock import FileLock

from .core import ROOT,ACTIONS,CONTRACT,OBS_SIZE,atomic_json,check_model,sha256
from .data import collect
from .environment import ArenaEnv
from .models import load_ppo,save_ppo,export_actor
from .teachers import BOT_NAMES,FROZEN_BOTS,verify_teacher
from .tracking import Tracker
from .training import load_config,new_model,resolve_model

BASE_KEYS=('obs','actions','teacher_id','scenario_id')
ARRAY_KEYS=BASE_KEYS+('reward','return_to_go','return_complete','transition')
PROBE_SEEDS=(940111,940107,940103,940101,940105)


def correction_options():
    return dict(revision=2,bootstrap_kickoff_weight=.65,student_prefix_fraction=.5,
                bootstrap_opponents='scorer',general_opponents='scorer,nexto,ripple,chronos,galactus')


def collection_config(cfg,bootstrap):
    focused=json.loads(json.dumps(cfg))
    if bootstrap:
        weights=focused['curriculum']['weights'];other=sum(v for k,v in weights.items() if k!='kickoff')
        kickoff=cfg['copy'].get('bootstrap_kickoff_weight',1.)
        focused['curriculum']['weights']={k:(kickoff if k=='kickoff' else (1-kickoff)*v/other if other else 0.) for k,v in weights.items()}
    return focused


def upgrade_copy(args):
    """Preserve weights/history, restart collection from the published student, and archive old active data."""
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    with FileLock(str(run/'train.lock'),timeout=0):
        cfg=json.loads((run/'config.json').read_text());state=json.loads((run/'copy_state.json').read_text())
        if cfg['copy'].get('revision',1)>=2:
            print('COPY_ALREADY_UPGRADED: resume with 21.');return
        if not cfg['copy'].get('history_free'):raise ValueError('Upgrade copy02, not the legacy copy01 run')
        selected=state.get('published',state['best']);check_model(run/selected['path'])
        # A single immutable backup makes an interrupted upgrade repeatable.
        backup=run/'copy_upgrade_v152_backup.json'
        if not backup.exists():atomic_json(backup,dict(config=cfg,state=state))
        state['archived_shards_v152']=state['shards'];state['shards']=[]
        state['resume']=dict(selected);state['phase']='collection';state['epoch']=0
        state['collection_stage']='correction_pending'
        atomic_json(run/'copy_state.json',state)
        cfg['copy'].update(correction_options(),epochs=2,lr=.0001)
        atomic_json(run/'config.json',cfg)
        print('COPY_UPGRADED: retained published student and validation; next resume collects varied corrections. No training files deleted.')


def load_shard(path):
    path=Path(path);meta=json.loads(Path(str(path)+'.json').read_text())
    if meta.get('contract')!=CONTRACT or meta.get('dataset_sha256')!=sha256(path):
        raise ValueError('Demonstration contract/hash mismatch')
    with np.load(path,allow_pickle=False) as z:
        arrays={k:z[k].copy() for k in BASE_KEYS}
        n=len(arrays['obs'])
        for key in ARRAY_KEYS[4:]:
            arrays[key]=z[key].copy() if key in z else np.zeros(n,dtype=bool if key in {'return_complete','transition'} else np.float32)
    n=len(arrays['obs'])
    if (not n or arrays['obs'].shape!=(n,OBS_SIZE) or not np.isfinite(arrays['obs']).all()
        or any(arrays[k].shape!=(n,) for k in ARRAY_KEYS[1:])):
        raise ValueError('Invalid demonstration shapes/observations')
    for key,upper in [('actions',len(ACTIONS)),('teacher_id',len(meta['teacher_names'])),
                      ('scenario_id',len(meta['scenario_names']))]:
        a=arrays[key]
        if not np.issubdtype(a.dtype,np.integer) or np.any(a<0) or np.any(a>=upper):
            raise ValueError('Invalid demonstration labels')
    if not np.isfinite(arrays['reward']).all() or not np.isfinite(arrays['return_to_go']).all():
        raise ValueError('Invalid demonstration rewards')
    return arrays,meta


def load_corpus(run,entries):
    chunks=[load_shard(Path(run)/e['path'])[0] for e in entries]
    if not chunks: raise ValueError('No demonstrations in corpus')
    return {k:np.concatenate([a[k] for a in chunks]) for k in ARRAY_KEYS}


def balance_weights(ids):
    unique,counts=np.unique(ids,return_counts=True)
    result=np.zeros(int(unique.max())+1,dtype=np.float32)
    result[unique]=len(ids)/(len(unique)*counts)
    return result


def return_weights(data):
    """Mild relative preference within each teacher; censored returns stay neutral."""
    ids=data['teacher_id'];weights=np.ones(len(ids),dtype=np.float32)
    returns=data.get('return_to_go');complete=data.get('return_complete')
    if returns is None or complete is None:return weights
    for teacher in np.unique(ids):
        mask=(ids==teacher)&complete.astype(bool)
        values=returns[mask]
        if len(values)<2 or float(values.std())<1e-6:continue
        signal=np.tanh((values-values.mean())/values.std());signal-=signal.mean()
        factors=1+.5*signal/max(1.,float(np.abs(signal).max()))
        weights[mask]=factors
    return weights


def remove_action_history_shortcut(model):
    layer=model.policy.mlp_extractor.policy_net[0]
    if not isinstance(layer,torch.nn.Linear) or layer.in_features!=OBS_SIZE:
        raise ValueError('History-free copying needs the standard NovaForge input layer')
    with torch.no_grad():
        layer.weight[:,-8:]=0
        for value in model.policy.optimizer.state.get(layer.weight,{}).values():
            if torch.is_tensor(value) and value.shape==layer.weight.shape:value[:,-8:]=0


def fit_epoch(model,data,seed,stop,batch_size=256,previous_dropout=.15,reward_weighting=True,history_free=True):
    rng=np.random.default_rng(seed);indices=rng.permutation(len(data['obs']))
    weights=balance_weights(data['teacher_id'])
    reward_weights=return_weights(data) if reward_weighting else np.ones(len(data['obs']),dtype=np.float32)
    transition_weights=1+2*data.get('transition',np.zeros(len(data['obs']),dtype=bool)).astype(np.float32)
    # Normalize within each teacher so transitions receive attention without suppressing a teacher.
    for teacher in np.unique(data['teacher_id']):
        mask=data['teacher_id']==teacher
        transition_weights[mask]/=transition_weights[mask].mean()
    reward_weights*=transition_weights
    for teacher in np.unique(data['teacher_id']):
        mask=data['teacher_id']==teacher
        reward_weights[mask]/=reward_weights[mask].mean()
    if history_free:remove_action_history_shortcut(model)
    policy=model.policy;policy.set_training_mode(True)
    total=weight_sum=0.;updates=seen=0
    for start in range(0,len(indices),batch_size):
        if stop.exists(): return dict(complete=False,updates=updates,seen=seen,loss=total/max(weight_sum,1))
        ids=indices[start:start+batch_size]
        x=data['obs'][ids].copy()
        # Discourage a shortcut that repeats the previous action indefinitely.
        if history_free:x[:,-8:]=0
        else:x[rng.random(len(ids))<previous_dropout,-8:]=0
        x=torch.as_tensor(x,device=model.device)
        y=torch.as_tensor(data['actions'][ids],device=model.device)
        w=torch.as_tensor(weights[data['teacher_id'][ids]]*reward_weights[ids],device=model.device)
        logits=policy.get_distribution(x).distribution.logits
        losses=torch.nn.functional.cross_entropy(logits,y,reduction='none')
        loss=(losses*w).mean()
        if not torch.isfinite(loss): raise ValueError('Nonfinite imitation loss')
        policy.optimizer.zero_grad(set_to_none=True);loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(),.5);policy.optimizer.step()
        if history_free:remove_action_history_shortcut(model)
        total+=float((losses.detach()*w).sum());weight_sum+=float(w.sum())
        updates+=1;seen+=len(ids)
    return dict(complete=True,updates=updates,seen=seen,loss=total/max(weight_sum,1))


def validate(model,data,teacher_names,scenario_names,stop=None):
    model.policy.set_training_mode(False)
    totals=defaultdict(float);groups=defaultdict(lambda:defaultdict(float))
    transitions=data.get('transition')
    if transitions is None:transitions=np.zeros(len(data['obs']),dtype=bool)
    with torch.inference_mode():
        for start in range(0,len(data['obs']),512):
            if stop is not None and stop.exists(): return None
            ids=slice(start,start+512)
            x=torch.as_tensor(data['obs'][ids],device=model.device)
            y=torch.as_tensor(data['actions'][ids],device=model.device)
            logits=model.policy.get_distribution(x).distribution.logits
            loss=torch.nn.functional.cross_entropy(logits,y,reduction='none').cpu().numpy()
            predicted=logits.argmax(-1).cpu().numpy();labels=data['actions'][ids]
            error=np.abs(ACTIONS[predicted]-ACTIONS[labels])
            for i,label in enumerate(labels):
                repeated=bool(np.max(np.abs(data['obs'][start+i,-8:]-ACTIONS[label]))<1e-6)
                values=dict(samples=1,loss=float(loss[i]),accuracy=predicted[i]==label,
                    repeat_previous_action_accuracy=repeated,
                    control_mae=float(error[i].mean()),button_accuracy=float((error[i,5:]==0).mean()))
                keys=[('teacher',teacher_names[int(data['teacher_id'][start+i])]),
                      ('scenario',scenario_names[int(data['scenario_id'][start+i])]),
                      ('transition','changed' if transitions[start+i] else 'held')]
                for key,value in values.items():
                    totals[key]+=value
                    for group in keys: groups[group][key]+=value
    def summary(row):
        n=int(row['samples'])
        return dict(samples=n,**{k:float(v)/n for k,v in row.items() if k!='samples'})
    result=summary(totals)
    result['by_teacher']={k[1]:summary(v) for k,v in groups.items() if k[0]=='teacher'}
    result['by_scenario']={k[1]:summary(v) for k,v in groups.items() if k[0]=='scenario'}
    result['by_transition']={k[1]:summary(v) for k,v in groups.items() if k[0]=='transition'}
    # Give each teacher equal weight when selecting the deployed checkpoint.
    result['balanced_loss']=sum(v['loss'] for v in result['by_teacher'].values())/len(result['by_teacher'])
    return result


def commit_model(model,run,state,validation=None):
    model.num_timesteps=state['collected_decisions']
    name=f'copy_r{state["round"]:06d}_e{state["epoch"]:04d}_{uuid.uuid4().hex[:8]}.zip'
    path=run/'checkpoints'/name
    save_ppo(model,path,initialization='frozen_teacher_copying',teacher=','.join(state['teachers']))
    record=dict(path=str(path.relative_to(run)),sha256=check_model(path)['sha256'],
                timesteps=state['collected_decisions'])
    state['resume']=record
    if validation is not None and (state['best_loss'] is None or validation['balanced_loss']<state['best_loss']):
        state['best_loss']=validation['balanced_loss'];state['best']=record
        state['best_validation']=validation
    atomic_json(run/'copy_state.json',state)
    published=state.get('published',state['best'])
    atomic_json(run/'latest.json',dict(path=published['path'],step=published['timesteps'],contract=CONTRACT))
    return record


def student_probe(model,cfg,stop):
    """Small monitoring check on the student's own trajectories, separate from teacher validation."""
    cfg=json.loads(json.dumps(cfg));cfg['curriculum']['adaptive']=False
    cfg['env'].update(episode_seconds=20,no_touch_seconds=21)
    rows=[];steps=active=forward=boost=0
    for seed in PROBE_SEEDS:
        for side in (0,1):
            if stop.exists():return None
            env=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=side)
            try:
                obs,_=env.reset(seed=seed)
                while True:
                    if stop.exists():return None
                    action=int(model.predict(obs,deterministic=True)[0]);control=ACTIONS[action]
                    steps+=1;active+=bool(np.any(np.abs(control)>1e-6));forward+=control[0]>0;boost+=control[6]>0
                    obs,_,terminal,truncated,info=env.step(action)
                    if terminal or truncated:rows.append(info);break
            finally:env.close()
    n=len(rows)
    return dict(trials=n,contact_fraction=sum(r['touches']>0 for r in rows)/n,
        score_fraction=sum(r['outcome']==1 for r in rows)/n,
        contact_score_fraction=sum(r['outcome']==1 and r['touches']>0 for r in rows)/n,
        concede_fraction=sum(r['outcome']==-1 for r in rows)/n,timeout_fraction=sum(r['timeout'] for r in rows)/n,
        touches_per_trial=sum(r['touches'] for r in rows)/n,active_control_fraction=active/max(steps,1),
        forward_throttle_fraction=float(forward)/max(steps,1),boost_fraction=float(boost)/max(steps,1))


def publish_by_probe(model,run,state,cfg,stop):
    """Prefer a student that actually reaches the ball; copy loss breaks monitoring ties."""
    candidates=[(state['best'],state['best_validation'])]
    if state['history']:candidates.append((state['resume'],state['history'][-1]['validation']))
    selected=state.get('published',state['best']);measured=state.get('last_student_probe')
    selected_validation=state.get('published_validation') or state['best_validation']
    def rank(probe,validation):
        # Historical probes without contact-backed goal counts receive no goal bonus.
        return (probe['contact_fraction'],probe.get('contact_score_fraction',0.),-probe['concede_fraction'],-validation['balanced_loss'])
    best_rank=rank(measured,selected_validation) if measured else None
    seen=set()
    for record,validation in candidates:
        if stop.exists():return None
        if record['sha256'] in seen:continue
        seen.add(record['sha256'])
        candidate=load_ppo(run/record['path'])
        probe=student_probe(candidate,cfg,stop);del candidate
        if probe is None:return None
        probe['checkpoint_sha256']=record['sha256']
        score=rank(probe,validation)
        if best_rank is None or score>best_rank:
            selected=record;selected_validation=validation;measured=probe;best_rank=score
    state['published']=dict(selected);state['published_validation']=selected_validation
    state['last_student_probe']=measured
    atomic_json(run/'copy_state.json',state)
    atomic_json(run/'latest.json',dict(path=selected['path'],step=selected['timesteps'],contract=CONTRACT))
    return measured


def train_copy(args):
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve(): raise ValueError('Run name must be one folder name')
    run.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        state_path=run/'copy_state.json';stop=run/'STOP'
        if args.resume:
            cfg=json.loads((run/'config.json').read_text());state=json.loads(state_path.read_text())
            options=cfg['copy'];names=options['teachers']
            if not options.get('history_free') or options.get('label_mode')!='final_executed':
                raise ValueError('This is a legacy copying run with transition-filtered labels. Start copy02 with launcher 21; copy01 remains available for viewing/comparison.')
            if state['teacher_lock_sha256']!=sha256(ROOT/'teachers.lock.json'):
                raise ValueError('Teacher lock changed; start a new copy run to use different teachers')
            check_model(run/state['resume']['path']);check_model(run/state['best']['path'])
        else:
            if (run/'config.json').exists() or state_path.exists():
                raise FileExistsError('Copy run exists; use --resume or a fresh name')
            cfg=load_config(args.config);cfg['workers']=1
            cfg['curriculum']['adaptive']=False
            names=[n.strip() for n in args.teachers.split(',')]
            if not names or len(set(names))!=len(names) or set(names)-set(FROZEN_BOTS):
                raise ValueError('Choose frozen nexto,ripple,chronos,galactus teachers without duplicates')
            if args.buffer_samples<args.samples: raise ValueError('buffer-samples must be at least samples per round')
            options=dict(teachers=names,samples=args.samples,validation_samples=args.validation_samples,
                buffer_samples=args.buffer_samples,epochs=args.epochs,lr=args.lr,seed=args.seed,
                previous_action_dropout=1.,reward_weighting=True,history_free=True,label_mode='final_executed',
                first_contact_bootstrap=True,contact_threshold=.75)
            options.update(correction_options())
            cfg['copy']=options
            state=dict(schema=1,teachers=names,teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),
                round=0,epoch=0,phase='validation',validation_shards=[],validation_decisions=0,
                shards=[],collected_decisions=0,gradient_updates=0,examples_seen=0,best_loss=None,
                best_validation=None,history=[])
        if names!=state['teachers']: raise ValueError('Stored teacher selection changed; start a new copy run')
        stop.unlink(missing_ok=True)
        for name in names: verify_teacher(name)
        torch.set_num_threads(cfg['threads'])
        tracker=Tracker(run,cfg,mode=args.wandb,continuous=args.forever)
        model=None;ready=False;started=time.monotonic();outcome='error'
        try:
            if args.resume:
                model=load_ppo(run/state['resume']['path'],device=cfg['device'])
                published=state.get('published',state['best'])
                atomic_json(run/'latest.json',dict(path=published['path'],step=published['timesteps'],contract=CONTRACT))
            else:
                env=ArenaEnv(cfg,opponent='scripted')
                try:
                    model=new_model(cfg,env)
                    if args.init:
                        source=load_ppo(resolve_model(args.init))
                        model.policy.load_state_dict(source.policy.state_dict())
                    remove_action_history_shortcut(model)
                    initial=run/'checkpoints/initial.zip';save_ppo(model,initial,initialization='copy_start')
                finally: env.close()
                state['best']=dict(path='checkpoints/initial.zip',sha256=check_model(initial)['sha256'],timesteps=0)
                state['resume']=dict(state['best'])
                state['published']=dict(state['best'])
                atomic_json(run/'config.json',cfg);atomic_json(state_path,state)
                atomic_json(run/'latest.json',dict(path='checkpoints/initial.zip',step=0,contract=CONTRACT))
            # Update the actor through supervised loss; value prediction stays frozen.
            for name,param in model.policy.named_parameters():
                if 'value_net' in name: param.requires_grad_(False)
            for group in model.policy.optimizer.param_groups: group['lr']=options['lr']
            start_round=state['round']
            def status(label,attempted=0,kept=0,log_metrics=True):
                metrics=dict(run=run.name,state=label,phase=state['phase'],round=state['round'],epoch=state['epoch'],
                    collected_decisions=state['collected_decisions'],collection_chunk_decisions=attempted,
                    collection_chunk_labels=kept,gradient_updates=state['gradient_updates'],
                    examples_seen=state['examples_seen'],best_loss=state['best_loss'],
                    active_labels=sum(e['samples'] for e in state['shards']),
                    collection_stage=state.get('collection_stage','validation'),
                    best_validation=state['best_validation'],session_seconds=time.monotonic()-started,
                    selected_validation=state.get('published_validation'),
                    last_student_probe=state.get('last_student_probe'),
                    continuous=args.forever,wandb=tracker.status())
                atomic_json(run/'status.json',metrics)
                if log_metrics:
                    tracker.log({'copy/round':state['round'],'copy/epoch':state['epoch'],
                        'copy/gradient_updates':state['gradient_updates'],'copy/examples_seen':state['examples_seen'],
                        'copy/collected_decisions':state['collected_decisions'],
                        'copy/chunk_decisions':attempted,'copy/chunk_labels':kept},state['collected_decisions'])
            def gather(validation=False):
                remaining=options['validation_samples']-state['validation_decisions'] if validation else options['samples']
                if remaining<=0: return
                label='validation' if validation else f'round_{state["round"]+1:06d}'
                path=run/'demonstrations'/f'{label}_{uuid.uuid4().hex[:8]}.npz'
                index=len(state['validation_shards']) if validation else state['round']
                seed=options['seed']+(1_000_000_000+index*100003 if validation else index*100003)
                bootstrap=not validation and options.get('first_contact_bootstrap',True) and state.get('last_student_probe',{}).get('contact_fraction',0)<options.get('contact_threshold',.75)
                state['collection_stage']='first_contact' if bootstrap else ('validation' if validation else 'general')
                collection_cfg=run/'config.json'
                if bootstrap:
                    focused=collection_config(cfg,True)
                    collection_cfg=run/'work'/f'first_contact_{uuid.uuid4().hex[:8]}.json'
                    atomic_json(collection_cfg,focused)
                student=None
                if not validation and state['collected_decisions']>0 and (not bootstrap or options.get('revision',1)>=2):
                    actor=run/'work'/f'prefix_{uuid.uuid4().hex[:8]}.pt'
                    best=load_ppo(run/state.get('published',state['best'])['path'])
                    export_actor(best,actor);student=str(actor)
                    del best
                state['phase']='validation' if validation else 'collection';status('copying')
                opponents='scripted' if validation else options.get('bootstrap_opponents','scorer') if bootstrap else options.get('general_opponents','scorer,nexto,ripple,chronos,galactus')
                summary=collect(SimpleNamespace(config=str(collection_cfg),replay_bank=None,
                    opponent=opponents,teacher=','.join(names),samples=remaining,out=str(path),seed=seed,
                    balanced_teachers=True,stop_path=stop,on_progress=lambda n,k:status('copying',n,k),
                    student_model=student,label_mode=options['label_mode'],balanced_scenarios=validation,
                    student_prefix_fraction=options.get('student_prefix_fraction',.25),
                    first_contact_fraction=.65 if bootstrap and options.get('revision',1)>=2 else (1. if bootstrap else (0. if validation else .25))))
                if summary.get('stopped'): stop.touch()
                if summary['samples']:
                    entry=dict(path=str(path.relative_to(run)),samples=summary['samples'],
                        attempted_decisions=summary['attempted_decisions'],sha256=summary['dataset_sha256'],
                        kept_by_teacher=summary['kept_by_teacher'],prefix_episodes=summary['prefix_episodes'],
                        kept_by_opponent=summary['kept_by_opponent'],
                        kept_by_scenario=summary['kept_by_scenario'],
                        collection_seconds=summary['collection_seconds'],
                        teacher_decisions_per_second=summary['teacher_decisions_per_second'],
                        reward_mean=summary['reward_mean'],complete_return_fraction=summary['complete_return_fraction'])
                    if validation:
                        state['validation_shards'].append(entry)
                        state['validation_decisions']+=summary['attempted_decisions']
                    else:
                        state['shards'].append(entry)
                        state['collected_decisions']+=summary['attempted_decisions']
                        # Keep full shards, removing old entries from the active RAM buffer.
                        while len(state['shards'])>1 and sum(e['samples'] for e in state['shards'])>options['buffer_samples']:
                            state['shards'].pop(0)
                        state['phase']='fit';state['epoch']=0
                    atomic_json(state_path,state)
                    if not validation:
                        tracker.log({'copy/collection_decisions_per_second':summary['teacher_decisions_per_second'],
                                     'copy/collection_seconds':summary['collection_seconds'],
                                     'copy/teacher_takeover_episodes':summary['prefix_episodes']},state['collected_decisions'])
            ready=True
            while state['validation_decisions']<options['validation_samples'] and not stop.exists(): gather(True)
            validation_data=load_corpus(run,state['validation_shards']) if state['validation_shards'] else None
            if not stop.exists():
                before=validate(model,validation_data,names,list(cfg['curriculum']['weights']),stop)
                if before is not None:
                    if state['best_loss'] is None: commit_model(model,run,state,before)
                    print('Initial held-out teacher-copy metrics:',json.dumps(before),flush=True)
            while not stop.exists() and (args.forever or state['round']-start_round<args.rounds):
                if state['phase']!='fit': gather(False)
                if stop.exists(): break
                train_data=load_corpus(run,state['shards'])
                while state['epoch']<options['epochs'] and not stop.exists():
                    state['phase']='fit';status('fitting')
                    result=fit_epoch(model,train_data,options['seed']+state['round']*1000+state['epoch'],
                        stop,previous_dropout=options['previous_action_dropout'],
                        reward_weighting=options.get('reward_weighting',True),history_free=options['history_free'])
                    state['gradient_updates']+=result['updates'];state['examples_seen']+=result['seen']
                    if not result['complete']: break
                    measured=validate(model,validation_data,names,list(cfg['curriculum']['weights']),stop)
                    if measured is None: break
                    state['epoch']+=1
                    row=dict(round=state['round']+1,epoch=state['epoch'],
                        collected_decisions=state['collected_decisions'],gradient_updates=state['gradient_updates'],
                        train_loss=result['loss'],validation=measured,
                        teacher_reward_mean=float(train_data['reward'].mean()),
                        complete_return_fraction=float(train_data['return_complete'].mean()))
                    record=commit_model(model,run,state,measured)
                    row['checkpoint_sha256']=record['sha256']
                    # Bounded metric history; full immutable checkpoints remain local.
                    state['history']=(state['history']+[row])[-2000:]
                    atomic_json(state_path,state)
                    tracker.log({'copy/train_loss':result['loss'],
                        'copy/teacher_reward_mean':row['teacher_reward_mean'],
                        'copy/complete_return_fraction':row['complete_return_fraction'],
                        **{'copy/validation_'+k:v for k,v in measured.items() if isinstance(v,(int,float))}},
                        state['collected_decisions'])
                    for kind in ['by_teacher','by_scenario','by_transition']:
                        tracker.log({f'copy/{kind}/{key}/{metric}':value for key,values in measured[kind].items()
                            for metric,value in values.items()},state['collected_decisions'])
                    status('fitting');print('COPY_EPOCH',json.dumps(row),flush=True)
                if not stop.exists():
                    probe=publish_by_probe(model,run,state,cfg,stop)
                    if probe is not None:
                        tracker.log({f'copy/student_{key}':value for key,value in probe.items() if isinstance(value,(int,float))},state['collected_decisions'])
                        print('COPY_STUDENT_PROBE',json.dumps(probe),flush=True)
                if not stop.exists():
                    state['round']+=1;state['epoch']=0;state['phase']='collection'
                    atomic_json(state_path,state)
            outcome='stopped' if stop.exists() else 'finished'
        except KeyboardInterrupt:
            outcome='stopped';stop.touch()
        finally:
            try:
                if ready:
                    # Preserve optimizer progress; watch/export keep the rollout-selected published model.
                    commit_model(model,run,state)
                    status(outcome)
            finally:
                tracker.finish(outcome)
                if ready: status(outcome,log_metrics=False)
        print(f'COPY_{outcome.upper()}: best student is {run}; teachers were never trained.',flush=True)


def validation_coverage_notes(validation,weights):
    notes=[]
    if not validation:
        return ['No validation result is available yet. Complete a fitting epoch before judging copying quality.']
    scenarios=validation.get('by_scenario',{})
    repeat=validation.get('repeat_previous_action_accuracy')
    if isinstance(repeat,(int,float)) and validation.get('accuracy',0)<=repeat+.02:
        notes.append('Copying accuracy is close to or below the repeat-previous-action baseline. Inspect transition-specific results and student rollouts before claiming improvement.')
    for name in ('kickoff','shot','defense','dribble','recovery','aerial','wall','replay'):
        if weights.get(name,0)<=0:continue
        count=int(scenarios.get(name,{}).get('samples',0))
        if count==0:
            notes.append(f'{name}: no held-out teacher action labels in this validation set; copying quality is unmeasured.')
        elif count<200:
            notes.append(f'{name}: only {count} held-out action labels; inspect separate gameplay trials before drawing a conclusion.')
    notes.append('Action agreement is measured on teacher trajectories. Evaluate the student controlling the car to assess playing strength; repeated validation selection is not a final test.')
    return notes


def report_copy(args):
    from .reporting import numbers,safe_url,evaluation_summaries,SCENARIOS
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve(): raise ValueError('Invalid run name')
    state=json.loads((run/'copy_state.json').read_text())
    published=state.get('published',state['best'])
    config=json.loads((run/'config.json').read_text())
    tracking=json.loads((run/'wandb_status.json').read_text()) if (run/'wandb_status.json').exists() else {}
    hashes={published['sha256'],state['best']['sha256']}
    for meta in (run/'checkpoints').glob('*.zip.json'):
        try: hashes.add(json.loads(meta.read_text())['sha256'])
        except (OSError,ValueError,KeyError): continue
    def clean_validation(value):
        if not isinstance(value,dict): return None
        keys={'samples','loss','balanced_loss','accuracy','control_mae','button_accuracy','repeat_previous_action_accuracy'}
        result=numbers(value,keys)
        for name,allowed in [('by_teacher',set(BOT_NAMES)),('by_scenario',SCENARIOS),('by_transition',{'changed','held'})]:
            result[name]={k:numbers(v,keys) for k,v in value.get(name,{}).items() if k in allowed}
        return result
    history=[]
    for raw in state['history'][-2000:]:
        row=numbers(raw,{'round','epoch','collected_decisions','gradient_updates','train_loss',
            'teacher_reward_mean','complete_return_fraction'})
        row['validation']=clean_validation(raw.get('validation'));history.append(row)
    active_collection={'by_teacher':defaultdict(int),'by_opponent':defaultdict(int),'by_scenario':defaultdict(int),'prefix_episodes':0}
    for entry in state['shards']:
        active_collection['prefix_episodes']+=int(entry.get('prefix_episodes',0))
        for key,allowed in [('by_teacher',BOT_NAMES),('by_opponent',BOT_NAMES),('by_scenario',SCENARIOS)]:
            for name,count in numbers(entry.get('kept_'+key,{}),allowed).items():active_collection[key][name]+=count
    report=dict(kind='frozen_teacher_copying',run=run.name,generated_utc=datetime.now(timezone.utc).isoformat(),
        teachers=[n for n in state['teachers'] if n in BOT_NAMES],
        teacher_lock_sha256=state['teacher_lock_sha256'],
        configuration=dict(copy=numbers(config['copy'],{'samples','validation_samples','buffer_samples',
            'epochs','lr','seed','previous_action_dropout','revision','bootstrap_kickoff_weight','student_prefix_fraction'}),reward_weighting=bool(config['copy'].get('reward_weighting',True)),
            collection_opponents={k:[n for n in config['copy'].get(k,'scripted').split(',') if n in BOT_NAMES] for k in ('bootstrap_opponents','general_opponents')},
            history_free=bool(config['copy'].get('history_free')),label_mode=config['copy'].get('label_mode','constant_executed'),
            first_contact_bootstrap=bool(config['copy'].get('first_contact_bootstrap')),
            reset_weights=numbers(config['curriculum']['weights'],SCENARIOS)),
        progress=numbers(state,{'round','epoch','collected_decisions','validation_decisions','gradient_updates','examples_seen','best_loss'}),
        best_checkpoint={k:published[k] for k in ['sha256','timesteps']},
        validation_best_checkpoint={k:state['best'][k] for k in ['sha256','timesteps']},
        best_validation=clean_validation(state['best_validation']),history=history,
        active_collection=active_collection,
        selected_validation=clean_validation(state.get('published_validation')),
        review_notes=validation_coverage_notes(state['best_validation'],config['curriculum']['weights']),
        student_probe=numbers(state.get('last_student_probe'),{'trials','contact_fraction','score_fraction',
            'contact_score_fraction',
            'concede_fraction','timeout_fraction','touches_per_trial','active_control_fraction',
            'forward_throttle_fraction','boost_fraction'}),
        probe_matches_best=bool(state.get('last_student_probe',{}).get('checkpoint_sha256')==published['sha256']),
        wandb_url=safe_url(tracking.get('url')),
        evaluations=evaluation_summaries(ROOT/'reports',published['sha256'],hashes),
        note='Supervised action-copy metrics, not match win rates. Shared simulator returns mildly weight expert labels; the original teachers reward functions are unknown. PPO is not used. Teacher rollout outcomes are not student outcomes.')
    if not config['copy'].get('history_free'):
        report['review_notes'].insert(0,'Legacy copy01 run: filtered transitions and previous-action inputs can inflate validation agreement. Use the corrected fresh copy02 workflow.')
    csv_out=io.StringIO();writer=csv.DictWriter(csv_out,['round','epoch','collected_decisions','train_loss','validation_loss','validation_accuracy'])
    writer.writeheader()
    for row in history:
        writer.writerow({**{k:row[k] for k in ['round','epoch','collected_decisions','train_loss']},
            'validation_loss':row['validation']['balanced_loss'],'validation_accuracy':row['validation']['accuracy']})
    payload=json.dumps(report,allow_nan=False).replace('<',r'\u003c')
    html='''<!doctype html><meta charset="utf-8"><title>Frozen teacher copying</title>
<style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:20px}td,th{padding:8px;text-align:left}svg{width:100%;height:250px}</style>
<h1>Frozen teacher copying</h1><p id="status"></p><p>Loss measures copying accuracy on separate teacher episodes. Playing strength requires simulator evaluations and offline matches.</p><p id="notes"></p>
<h2>Held-out loss over training epochs</h2><svg id="chart" viewBox="0 0 900 250"></svg>
<h2>Student's own kickoff monitoring</h2><p>Five standard kickoff starts on both sides against the scripted opponent. This is monitoring feedback used in selection, not an independent strength test.</p><pre id="probe"></pre>
<h2>Best student's teacher-copy metrics</h2><pre id="metrics"></pre>
<script id="data" type="application/json">'''+payload+'''</script><script>
const d=JSON.parse(document.getElementById('data').textContent);document.getElementById('status').textContent=d.run+' | '+d.progress.collected_decisions+' collected decisions | '+d.progress.gradient_updates+' supervised updates';document.getElementById('metrics').textContent=JSON.stringify(d.best_validation,null,2);
document.getElementById('notes').textContent=d.review_notes.join(' • ');
document.getElementById('probe').textContent=JSON.stringify({matches_best_checkpoint:d.probe_matches_best,...d.student_probe},null,2);
const ns='http://www.w3.org/2000/svg',svg=document.getElementById('chart'),p=d.history.map((r,i)=>({x:i,y:r.validation.balanced_loss}));if(p.length){let lo=Math.min(...p.map(v=>v.y)),hi=Math.max(...p.map(v=>v.y));if(lo===hi){lo-=.1;hi+=.1}const line=document.createElementNS(ns,'polyline');line.setAttribute('points',p.map(v=>`${40+820*v.x/Math.max(1,p.length-1)},${215-180*(v.y-lo)/(hi-lo)}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#176bd4');line.setAttribute('stroke-width','2');svg.append(line)}
</script>'''
    out=ROOT/'reports'/f'{run.name}_copy_report_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.zip'
    out.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=out.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w+b') as f:
            with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('report.json',json.dumps(report,indent=2,allow_nan=False));z.writestr('training.csv',csv_out.getvalue())
                z.writestr('progress.html',html);z.writestr('README.txt','Open progress.html. Upload this ZIP for review. It contains selected metrics and hashes, without weights, raw trajectories or credentials.\n')
            f.flush();os.fsync(f.fileno())
        os.replace(temp,out)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    print(f'COPY_REPORT_READY: {out}')
