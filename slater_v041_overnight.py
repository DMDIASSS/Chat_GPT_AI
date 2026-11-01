"""Slater v0.4.1 — AFK evolutionary PPO league, safe resume, no auto champion overwrite.

One learner at a time. Six frozen opponents all have scripted kickoffs;
student does not. Every branch gets bounded PPO and an independent paired
screen, strong finalists get another holdout. Never edits protected models.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import torch

from slater_v041_core import (DEFAULT_CONFIG, RIVAL_NAMES, atomic_json,find_model,
    paired_scores,process_lock,read_json,sha256,should_promote,space_preflight,
    specs_for_generation,validate_config,validate_pool,verify_protected,promotion_alpha,
    holdout_seed_count,evaluation_seed_base)

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'slater_v041_config.json'

def root_for_run(root,run):return root/'data'/'isolated'/'v041_overnight'/run

def write_checkpoint(path,doc):
    """Fsync then atomic rename. A partial write never appears as a checkpoint."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(f'Refusing checkpoint overwrite {path}')
    tmp=path.with_name(path.name+'.incomplete')
    if tmp.exists():tmp.unlink()  # previous interrupted atomic write, never a complete checkpoint
    with tmp.open('xb') as handle:
        torch.save(doc,handle);handle.flush();os.fsync(handle.fileno())
    os.replace(tmp,path)

def mutate_from(source,target,scale,seed):
    """Zero-mean Gaussian perturbation with RMS-relative scale per tensor.

    Actor-only changes. Reset Adam actor moments so old momentum doesn't cancel
    the mutation. Keep critic + critic optimizer (same reward/task). Small
    mutations are 1.2% RMS; big mutations 6.5% RMS, not 6.5% accuracy.
    """
    if not (0.0<scale<=.15):raise ValueError('Unsafe mutation scale')
    source=Path(source);target=Path(target)
    doc=torch.load(source,map_location='cpu',weights_only=True)
    if not isinstance(doc,dict) or not all(k in doc for k in
            ('actor','critic','actor_optimizer','critic_optimizer','global_updates')):
        raise ValueError('Mutations require FULL checkpoint; exported nexto-model.pt is opponent-only')
    generator=torch.Generator(device='cpu').manual_seed(seed)
    actor=doc['actor'];changed=0;energy=0.
    for name,weight in actor.items():
        if not torch.is_tensor(weight) or not weight.is_floating_point() or weight.numel()<8:
            continue
        rms=float(weight.float().square().mean().sqrt().item())
        std=scale*max(rms,1e-4)
        noise=torch.randn(weight.shape, generator=generator, dtype=torch.float32)*std
        noise.clamp_(-3.0*std,3.0*std)
        replacement=weight+noise.to(dtype=weight.dtype)
        if not torch.isfinite(replacement).all():raise FloatingPointError(f'Nonfinite mutation in {name}')
        actor[name]=replacement;changed+=1;energy+=float(noise.square().sum().item())
    if changed<4:raise RuntimeError('Actor weights too small/unexpected architecture')
    doc['actor_optimizer']['state']={}
    doc['meta']=dict(doc.get('meta',{}),v041_mutation={
        'source_sha256':sha256(source),'scale':scale,'seed':seed,'tensors_changed':changed,
        'squared_perturbation':energy})
    write_checkpoint(target,doc)
    return doc['meta']['v041_mutation']

def find_latest_trial_checkpoint(trial_dir,trial_id):
    """Recover only *valid* saved PPO states; reject corrupt/orphaned checkpoints.

    Reports are advisory. The checkpoint itself is the durable boundary. A bad
    latest checkpoint cannot silently replace an earlier valid one.
    """
    rows=[]
    for p in trial_dir.glob(f'{trial_id}_u*.pt'):
        try: update=int(p.stem.split('_u')[-1])
        except ValueError:continue
        try:
            doc=torch.load(p,map_location='cpu',weights_only=True)
            required=('actor','critic','actor_optimizer','critic_optimizer','global_updates')
            if not isinstance(doc,dict) or any(k not in doc for k in required):continue
            if doc['global_updates'] != update or not isinstance(doc['actor'],dict):continue
            if any(not torch.isfinite(v).all() for v in doc['actor'].values()
                   if torch.is_tensor(v) and v.is_floating_point()):continue
            report=p.with_suffix('.json')
            if not report.is_file():
                atomic_json(report,{'recovered_after_crash':True,
                    'global_updates':update,'checkpoint_sha256':sha256(p)})
        except Exception:
            continue
        rows.append((update,p))
    return max(rows)[1] if rows else None

def relative(root,path):return str(Path(path).resolve().relative_to(root.resolve())).replace('\\','/')

def run_subprocess(root,argv,log_file):
    """Append-only logs, child process only, fail closed on nonzero exit."""
    log_file.parent.mkdir(parents=True,exist_ok=True)
    with log_file.open('a',encoding='utf-8') as log:
        log.write('\n=== '+datetime.now(timezone.utc).isoformat()+' '+repr(argv)+' ===\n');log.flush()
        proc=subprocess.Popen([sys.executable,'-u',*argv],cwd=root,stdout=log,
                              stderr=subprocess.STDOUT)
        while proc.poll() is None:
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:pass
        code=proc.returncode
        log.write(f'\n=== EXIT {code} ===\n');log.flush();os.fsync(log.fileno())
    if code:raise RuntimeError(f'Child exit code {code}; inspect {log_file}')


def replay_arguments(root,config,run_dir):
    if not config.get('replay_starts'):return []
    saved=read_json(run_dir/'replay_starts_manifest.json')
    path=(root/config['replay_starts']).resolve()
    if not saved or saved['path']!=str(path) or saved['sha256']!=sha256(path):
        raise RuntimeError('Replay reset dataset differs from preflight manifest')
    return ['--replay-starts',str(path),'--replay-starts-sha',saved['sha256'],
            '--replay-start-probability',str(config.get('replay_start_probability',.2))]

def train_branch(root,config,manifest_path,gen,spec,leader,large_root,archive_source,run_dir):
    kind=spec['kind'];trial_id=f'g{gen:05d}_{kind}'
    folder=run_dir/'trials'/trial_id;folder.mkdir(parents=True,exist_ok=True)
    result_path=folder/'completed.json'
    result=read_json(result_path)
    if result:
        final=root/result['final'];
        if sha256(final)!=result['sha256']:raise RuntimeError(f'Saved {kind} hash mismatch')
        return final
    parent={'leader':leader,'large_root':large_root,'archive':archive_source}[spec['base']]
    if parent is None:raise RuntimeError(f'Missing parent {spec["base"]} for {kind}')
    parent=Path(parent)
    scale=0. if kind=='ppo_continuation' else (
        config['large_mutation'] if kind=='large_root' else config['small_mutation'])
    initial=folder/'seed.pt'
    if not initial.exists():
        if scale==0.:
            # Preserve actor AND Adam state for the unperturbed PPO control.
            doc=torch.load(parent,map_location='cpu',weights_only=True)
            write_checkpoint(initial,doc)
            info={'source_sha256':sha256(parent),'scale':0.,'tensors_changed':0,
                  'kind':'unperturbed_ppo_continuation'}
        else:
            info=mutate_from(parent,initial,scale,seed=101+gen*100003+sum(map(ord,kind)))
        atomic_json(folder/'mutation.json',info)
    original=torch.load(initial,map_location='cpu',weights_only=True)
    goal=int(original['global_updates'])+config['updates_per_trial']
    last=find_latest_trial_checkpoint(folder,trial_id)
    source=last if last is not None else initial
    current=torch.load(source,map_location='cpu',weights_only=True)
    remaining=goal-int(current['global_updates'])
    if remaining<0:raise RuntimeError(f'Past intended training update target in {trial_id}')
    if remaining:
        is_large=(kind=='large_root' or kind.startswith('large_child'))
        argv=['slater_v041_worker.py','--source',relative(root,source),
              '--leader-checkpoint',relative(root,leader),
              '--manifest',relative(root,manifest_path),'--run',trial_id,
              '--output-dir',relative(root,folder),
              '--seed',str(110000+gen*10009+sum(map(ord,kind))),
              '--updates',str(remaining),'--rollout-steps',str(config['rollout_steps']),
              '--episode-steps',str(config['episode_steps']),
              '--actor-lr',str(config['actor_lr_large'] if is_large else config['actor_lr_small']),
              '--teacher-weight',str(config['teacher_weight_large'] if is_large else config['teacher_weight_small']),
              '--target-kl',str(config.get('target_kl',DEFAULT_CONFIG['target_kl'])),
              '--training-reset',config.get('training_reset','kickoff'),
              '--rlbot-delay' if config.get('rlbot_delay',False) else '--no-rlbot-delay',
              '--epochs',str(config['epochs']),'--minibatch',str(config['minibatch'])]
        argv.extend(replay_arguments(root,config,run_dir))
        run_subprocess(root,argv,folder/'training.log')
    last=find_latest_trial_checkpoint(folder,trial_id)
    if last is None:raise RuntimeError(f'No finished PPO checkpoint for {kind}')
    payload={'trial':kind,'generation':gen,'final':relative(root,last),'sha256':sha256(last),
             'parent_sha':sha256(parent),'mutation_scale':scale}
    atomic_json(result_path,payload)
    return last

def check_eval_report(path,source_sha,leader_sha,*,expected=None):
    doc=read_json(path)
    if doc is None:return None
    if doc['candidate_sha']!=source_sha or doc['leader_sha']!=leader_sha:
        raise RuntimeError(f'Evaluation report belongs to different checkpoint: {path}')
    if expected is not None:
        for key,value in expected.items():
            actual=doc.get(key) if key=='manifest_sha' else doc['result'].get(key)
            if actual != value:raise RuntimeError(f'Evaluation {key} mismatch: {path}')
        rows=doc['result']['records']
        seed_ids={expected['seed_base']+j*997 for j in range(expected['seeds'])}
        keys={(r['seed'],r['side'],r['rival']) for r in rows}
        required={(s,side,rival) for s in seed_ids for side in ('blue','orange') for rival in RIVAL_NAMES}
        if keys!=required:raise RuntimeError(f'Incomplete or wrong evaluation seeds: {path}')
    # Recompute evidence from raw pairs, including when reading old reports.
    return paired_scores(doc['result']['records'])

def evaluate_branch(root,cfg,manifest,run_dir,gen,kind,candidate,leader,*,holdout=False):
    folder=run_dir/'evaluations'/f'g{gen:05d}';folder.mkdir(parents=True,exist_ok=True)
    label=kind+('_holdout' if holdout else '_screen')
    out=folder/f'{label}.json'
    # Independent holdout changes each generation; no reuse of screen seeds.
    seed=evaluation_seed_base(gen,holdout)
    seeds=holdout_seed_count(cfg['promotion_seeds'],gen,
        cfg.get('promotion_error_budget',DEFAULT_CONFIG['promotion_error_budget'])) if holdout else cfg['screen_seeds']
    expected={'manifest_sha':sha256(manifest),'seed_base':seed,
              'seeds':seeds,
              'episode_steps':cfg['eval_steps'],'rlbot_delay':cfg.get('rlbot_delay',False)}
    known=check_eval_report(out,sha256(candidate),sha256(leader),expected=expected)
    if known is not None:return known
    argv=['slater_v041_eval.py','--candidate',relative(root,candidate),
          '--leader',relative(root,leader),'--manifest',relative(root,manifest),
          '--out',relative(root,out),'--seed',str(seed),
          '--seeds',str(seeds),
          '--rlbot-delay' if cfg.get('rlbot_delay',False) else '--no-rlbot-delay',
          '--steps',str(cfg['eval_steps'])]
    run_subprocess(root,argv,folder/f'{label}.log')
    known=check_eval_report(out,sha256(candidate),sha256(leader),expected=expected)
    if known is None:raise RuntimeError('Evaluation did not write a report')
    return known

def loading_state(root,cfg,run_dir,manifest):
    state_path=run_dir/'league_state.json'
    state=read_json(state_path)
    if state:
        if state.get('config_sha')!=sha256(root/'slater_v041_config.json'):
            raise RuntimeError('Config changed during run. Restore exact config or use a NEW run_name.')
        if state.get('manifest_sha')!=sha256(manifest):
            raise RuntimeError('Opponent manifest changed during run')
        for item in [state['leader'],*state.get('archive',[])]:
            if not Path(root/item['path']).is_file() or sha256(root/item['path'])!=item['sha256']:
                raise RuntimeError(f'League saved checkpoint missing/changed: {item["path"]}')
        return state
    source=(root/'data/isolated/v040_multirival_campaign01_u0070.pt').resolve()
    if not source.is_file():raise FileNotFoundError(f'V70 PPO source missing {source}')
    state={'version':'v0.4.1','run':cfg['run_name'],'generation':1,'leader':{
               'path':relative(root,source),'sha256':sha256(source),'kind':'v70_baseline'},
           'archive':[],'history':[], 'config_sha':sha256(root/'slater_v041_config.json'),
           'manifest_sha':sha256(manifest),'note':'All champions untouched. Simulator-best is provisional.'}
    atomic_json(state_path,state)
    return state

def retire_generated_branch(root,run_dir,gen,kind,preserve):
    """Remove only our OWN disposable training candidates, never user checkpoints."""
    folder=run_dir/'trials'/f'g{gen:05d}_{kind}'
    if not folder.is_dir():return
    for p in folder.glob('*.pt'):
        if p.resolve() not in preserve:
            p.unlink(missing_ok=True)
    # Keep reports, logs, and metadata for analysis.

def save_archive(run_dir,state):
    atomic_json(run_dir/'league_state.json',state)
    atomic_json(run_dir/'leader.json',state['leader'])

def start_loop(root,cfg,run_dir,manifest):
    state=loading_state(root,cfg,run_dir,manifest)
    pause=run_dir/'pause.request'
    while not pause.exists() and (cfg['limit_generations']==0 or state['generation']<=cfg['limit_generations']):
        space_preflight(root,cfg['min_disk_gb'])
        gen=state['generation'];leader=root/state['leader']['path']
        evaluation_seed_base(gen,True)  # stop before training if ranges run out
        archived=[root/x['path'] for x in state.get('archive',[]) if (root/x['path']).is_file()]
        previous=archived[-1] if archived else None
        specs=specs_for_generation(gen,len(archived))
        candidates={};failed={};large_root=None
        for spec in specs:
            if pause.exists():break
            space_preflight(root,cfg['min_disk_gb'])
            kind=spec['kind']
            try:
                final=train_branch(root,cfg,manifest,gen,spec,leader,large_root,previous,run_dir)
                candidates[kind]=final
                if kind=='large_root':large_root=final
            except Exception as exc:
                failed[kind]=repr(exc)
                atomic_json(run_dir/'trials'/f'g{gen:05d}_{kind}'/'failure.json',
                            {'kind':kind,'error':repr(exc),'utc':datetime.now(timezone.utc).isoformat()})
                print(f'V041_BRANCH_FAILED {gen} {kind}: {exc}',flush=True)
                if kind=='large_root':large_root=None
                continue
        if pause.exists():break
        rankings=[]
        for kind,final in candidates.items():
            try:
                screen=evaluate_branch(root,cfg,manifest,run_dir,gen,kind,final,leader)
                rankings.append((screen['mean_paired_delta'],screen['resolved_pairs'],kind,final,screen))
                print(f'V041_SCREEN g={gen} {kind} score={screen["mean_paired_delta"]:+.3f} resolved={screen["resolved_pairs"]}',flush=True)
            except Exception as exc:
                failed[kind]='screen failed: '+repr(exc)
                print(f'V041_SCREEN_FAILED {kind}: {exc}',flush=True)
        rankings.sort(key=lambda x:(x[0],x[1]),reverse=True)
        if not rankings:
            raise RuntimeError('All candidates failed training or evaluation. Stopped safely; inspect *.log')
        winner=None;reason='no candidate passed independent holdout'
        # Up to two finalists. Screen never by itself promotes a model.
        for score,resolved,kind,final,screen in rankings[:2]:
            if score<=0:continue
            try:
                holdout=evaluate_branch(root,cfg,manifest,run_dir,gen,kind,final,leader,holdout=True)
                ok,verdict=should_promote(holdout,margin=cfg['promote_margin'],
                       min_resolved=max(10, 2*holdout['seed_evidence']['seed_count']),
                       alpha=promotion_alpha(gen,finalists=2,
                           budget=cfg.get('promotion_error_budget',DEFAULT_CONFIG['promotion_error_budget'])))
                print(f'V041_HOLDOUT {kind} {holdout["mean_paired_delta"]:+.3f} {verdict}',flush=True)
                if ok and (winner is None or holdout['mean_paired_delta']>winner[0]):
                    winner=(holdout['mean_paired_delta'],kind,final,holdout)
                reason=verdict
            except Exception as exc:
                failed[kind]='holdout failed: '+repr(exc)
        old_leader=state['leader']
        if winner is not None:
            score,kind,final,_=winner
            state['archive'].append(old_leader)
            state['archive']=state['archive'][-cfg['max_archive']:]
            state['leader']={'path':relative(root,final),'sha256':sha256(final),
                             'kind':kind,'generation':gen,'simulator_holdout_delta':score,
                             'status':'PROVISIONAL_NOT_LIVE_RLBOT_VERIFIED'}
            state['leader']['promotion_evidence']=winner[3]['seed_evidence']
            state['leader']['promotion_alpha']=promotion_alpha(gen,finalists=2,
                budget=cfg.get('promotion_error_budget',DEFAULT_CONFIG['promotion_error_budget']))
            reason='provisionally_promoted_'+kind
        state['history'].append({'generation':gen,'leader_before':old_leader,
                    'leader_after':state['leader'],'reason':reason,
                    'rankings':[{'kind':x[2],'screen_delta':x[0],'resolved':x[1]} for x in rankings],
                    'failed':failed})
        state['generation']=gen+1
        # Atomic state first: if a crash occurs now, winner is retained on disk.
        save_archive(run_dir,state)
        preserve={ (root/state['leader']['path']).resolve(),
                  *((root/x['path']).resolve() for x in state['archive']) }
        for kind in candidates:
            retire_generated_branch(root,run_dir,gen,kind,preserve)
        if len(state['history'])>1000:
            state['history']=state['history'][-1000:];save_archive(run_dir,state)
        print(f'V041_GENERATION_COMPLETE {gen} {reason} leader={state["leader"]["path"]}',flush=True)
    print('V041_PAUSED' if pause.exists() else 'V041_GENERATION_LIMIT',flush=True)

def preflight(root,cfg,run_dir):
    for filename in ('slater_v041_core.py','slater_v041_worker.py','slater_v041_eval.py',
                     'slater_v040_multirival.py','slater_nexto_kickoff_v037a.py',
                     'slater_cycle9_native_ppo_v025.py','afk_team_research.py','slater_ppo.py',
                     'slater_replay_starts.py'):
        if not (root/filename).is_file():raise FileNotFoundError(f'Missing project dependency {filename}')
    pool=validate_pool(root,cfg)
    # Load every model, verify common Nexto obs/action compatibility before unattended run.
    from slater_v041_worker import load_pool
    load_pool(root,pool)
    space_preflight(root,cfg['min_disk_gb'])
    if (root/'data/isolated/v040_multirival_campaign01_u0070.pt').is_file():
        doc=torch.load(root/'data/isolated/v040_multirival_campaign01_u0070.pt',
                       map_location='cpu',weights_only=True)
        if not all(k in doc for k in ('actor','critic','actor_optimizer','critic_optimizer')):
            raise ValueError('u70 PPO source lacks training states')
    else:raise FileNotFoundError('u70 PPO source checkpoint missing')
    manifest=run_dir/'opponents_manifest.json'
    if manifest.exists():
        saved=read_json(manifest)
        if saved!=pool:raise RuntimeError('Opponent model changed since previous run')
    else:
        run_dir.mkdir(parents=True,exist_ok=True)
        atomic_json(manifest,pool)
    if cfg.get('replay_starts'):
        from slater_replay_starts import ReplayStartBank
        path=(root/cfg['replay_starts']).resolve()
        bank=ReplayStartBank(path)
        bank.sample(0)  # verify decoded state before a training process starts
        entry={'path':str(path),'sha256':sha256(path),'eligible_frames':len(bank.indices)}
        dataset_manifest=run_dir/'replay_starts_manifest.json'
        if dataset_manifest.exists():
            if read_json(dataset_manifest)!=entry:raise RuntimeError('Replay reset dataset changed since previous run')
        else:atomic_json(dataset_manifest,entry)
    return manifest

def smoke_run(root,cfg,run_dir,manifest):
    """Real Windows one-update PPO and two-sided six-opponent evaluation, isolated."""
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run=f'smoke_{stamp}'
    folder=run_dir/'smoke'/run
    folder.mkdir(parents=True,exist_ok=False)
    parent=root/'data/isolated/v040_multirival_campaign01_u0070.pt'
    initial=folder/'seed.pt'
    mutate_from(parent,initial,cfg['small_mutation'],seed=27711)
    run_subprocess(root,['slater_v041_worker.py','--source',relative(root,initial),
            '--leader-checkpoint',relative(root,parent),
            '--manifest',relative(root,manifest),'--run',run,
            '--output-dir',relative(root,folder),'--seed','27722',
            '--updates','1','--rollout-steps','256','--episode-steps','240',
            '--actor-lr',str(cfg['actor_lr_small']),
            '--teacher-weight',str(cfg['teacher_weight_small']),
            '--target-kl',str(cfg.get('target_kl',DEFAULT_CONFIG['target_kl'])),
            '--training-reset',cfg.get('training_reset','kickoff'),
            '--rlbot-delay' if cfg.get('rlbot_delay',False) else '--no-rlbot-delay',
            '--epochs','1','--minibatch','64',
            *replay_arguments(root,cfg,run_dir)],folder/'training.log')
    trained=find_latest_trial_checkpoint(folder,run)
    if trained is None:raise RuntimeError('Smoke PPO did not produce a checkpoint')
    out=folder/'paired_eval.json'
    run_subprocess(root,['slater_v041_eval.py',
         '--candidate',relative(root,trained),'--leader',relative(root,parent),
         '--manifest',relative(root,manifest),'--out',relative(root,out),
         '--seed','332244','--seeds','1','--steps','180',
         '--rlbot-delay' if cfg.get('rlbot_delay',False) else '--no-rlbot-delay'],folder/'evaluation.log')
    if not out.is_file():raise RuntimeError('Smoke failed to write paired evaluation')
    print('V041_SMOKE_PASS',relative(root,folder),flush=True)
    print('V041_SMOKE_TRAIN_LOG',relative(root,folder/'training.log'),flush=True)
    print('V041_SMOKE_EVAL_LOG',relative(root,folder/'evaluation.log'),flush=True)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('preflight','smoke','start','resume','pause','status'))
    args=p.parse_args(argv)
    root=Path.cwd().resolve()
    cfg=validate_config(read_json(root/'slater_v041_config.json'))
    run_dir=root_for_run(root,cfg['run_name']);pause=run_dir/'pause.request'
    if args.command=='status':
        print(json.dumps({'state':read_json(run_dir/'league_state.json'),
              'paused':pause.exists(),'root':str(run_dir)},indent=2));return
    if args.command=='pause':
        run_dir.mkdir(parents=True,exist_ok=True)
        if not pause.exists():pause.write_text('pause requested; finish current training/eval before exiting\n')
        print('V041_PAUSE_REQUESTED',pause);return
    with process_lock(run_dir/'.overnight.lock'):
        manifest=preflight(root,cfg,run_dir)
        print('V041_PREFLIGHT_PASS',json.dumps({n:relative(root,root/info['path']) for n,info in read_json(manifest).items()},indent=2),flush=True)
        if args.command=='preflight':return
        if args.command=='smoke':
            smoke_run(root,cfg,run_dir,manifest)
            return
        if args.command=='start' and pause.exists():
            raise RuntimeError('Paused run: use resume instead of start')
        if args.command=='resume':pause.unlink(missing_ok=True)
        start_loop(root,cfg,run_dir,manifest)

if __name__=='__main__':main()
