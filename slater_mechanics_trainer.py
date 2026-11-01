"""Focused mechanics curriculum from a protected native checkpoint, not a league.

Compare existing models first; practice one physical skill at a time. Every
frozen rival has Nexto's scripted kickoff enabled. All outputs are isolated.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
import hashlib
from pathlib import Path
import random
import time

import numpy as np
import torch

from slater_mechanics_core import STAGES,mastery_verdict
from slater_mechanics_env import MechanicsEnv,MechanicsCritic,collect_batched
from slater_mechanics_eval import load_actor,compare_models,evaluate_stage,retention_check
from slater_ppo import trust_region_update
from slater_v041_core import atomic_json,read_json,sha256,process_lock
from slater_v041_overnight import write_checkpoint

ROOT=Path(__file__).resolve().parent
DEFAULT_CONFIG={
    'source_checkpoint':'data/isolated/v040_multirival_campaign01_u0070.pt',
    'run_name':'mechanics01','opponents':{},'n_envs':4,'steps_per_env':256,
    'actor_lr':1e-5,'critic_lr':1e-4,'epochs':3,'minibatch':128,
    'target_kl':.015,'mechanic_anchor':.02,'retention_anchor':.30,
    'updates_per_stage':200,'eval_every':20,'mastery_seeds':16,
    'retention_seeds':8,'retention_seconds':30,'episode_seconds':6,
    'allowed_goal_diff_drop_per_minute':.25,'seed':20261012,
}


def validate_config(cfg):
    bounds={'n_envs':(2,16),'steps_per_env':(32,2048),'epochs':(1,8),
        'minibatch':(16,4096),'updates_per_stage':(1,10000),'eval_every':(1,10000),
        'mastery_seeds':(12,64),'retention_seeds':(4,64)}
    for key,(low,high) in bounds.items():
        if type(cfg[key]) is not int or not low<=cfg[key]<=high:raise ValueError(f'Invalid {key}')
    for key,(low,high) in {'actor_lr':(1e-7,5e-5),'critic_lr':(1e-6,.001),
        'target_kl':(.0001,.05),'mechanic_anchor':(0,.2),'retention_anchor':(.1,1.),
        'retention_seconds':(8,300),'episode_seconds':(3,15),
        'allowed_goal_diff_drop_per_minute':(0,.5)}.items():
        if not np.isfinite(cfg[key]) or not low<=cfg[key]<=high:raise ValueError(f'Invalid {key}')
    name=cfg['run_name']
    if not name or not name.replace('_','').replace('-','').isalnum() or len(name)>40:
        raise ValueError('Invalid run name')
    if cfg['minibatch']>cfg['n_envs']*cfg['steps_per_env']:raise ValueError('Minibatch larger than rollout')
    if type(cfg['seed']) is not int or not 1<=cfg['seed']<100_000_000:raise ValueError('Invalid seed')
    return cfg


def known_candidates(root):
    from slater_research.checkpoint import CYCLE9
    paths={'V70':'data/isolated/v040_multirival_campaign01_u0070.pt',
        'V60':'data/isolated/slater_v027_campaign01_u0060.pt','Cycle9':CYCLE9,
        'OG_Champion':'data/autoleague/champion.pt',
        'AFK_verified':'data/afk_improved/best_verified.pt'}
    candidates={n:(root/p).resolve() for n,p in paths.items() if (root/p).is_file()}
    for folder in sorted((root/'data/isolated/v041_overnight').glob('*')):
        state=read_json(folder/'league_state.json')
        if state:
            leader=state['leader'];p=(root/leader['path']).resolve()
            if not p.is_file() or sha256(p)!=leader['sha256']:
                raise RuntimeError(f'League leader changed or missing: {p}')
            candidates['league_'+folder.name]=p
    return candidates


def model_paths(root,source,cfg):
    paths={'nexto':root/'vendor/nexto/nexto-model.pt','frozen_start':source}
    for name,path in cfg['opponents'].items():
        if name in paths:raise ValueError(f'Reserved rival name {name}')
        paths[name]=(root/path).resolve()
    return paths


def tournament_candidates(root,report_path,limit=3):
    """Use highest ranked compatible native actors; validate saved hashes."""
    report=read_json((root/report_path).resolve())
    if not report or 'leaderboard' not in report:raise ValueError('Missing round-robin leaderboard')
    candidates={}
    for row in report['leaderboard']:
        if row['kind'] not in ('NATIVE','NEXTO_TS'):continue
        path=(root/row['model']).resolve()
        if sha256(path)!=row['sha256']:raise RuntimeError(f'Tournament model changed: {path}')
        candidates[f"rank_{row['rank']}_{path.stem}"]=path
        if len(candidates)>=limit:break
    return candidates


def select_source(root,cfg,args):
    if getattr(args,'selection',None):
        report=read_json((root/args.selection).resolve())
        if not report:raise ValueError('Missing model comparison report')
        source=Path(report['recommended_source'])
        if sha256(source)!=report['recommended_source_sha256']:
            raise RuntimeError('Selected model changed since comparison')
        print('MECHANICS_SOURCE',report['selection_status'],source,flush=True)
        return source.resolve()
    return (root/(getattr(args,'source',None) or cfg['source_checkpoint'])).resolve()


def train(root,cfg,source,*,smoke=False,resume=False,updates_override=None):
    validate_config(cfg)
    if smoke:
        cfg=dict(cfg,run_name='smoke_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'),
                 n_envs=2,steps_per_env=64,epochs=1,minibatch=64)
    run_dir=root/'data/isolated/mechanics_curriculum'/cfg['run_name']
    if run_dir.exists() and not resume:raise FileExistsError(f'Run exists: {run_dir}; use resume or a new name')
    paths=model_paths(root,source,cfg)
    manifest={n:{'path':str(p),'sha256':sha256(p)} for n,p in paths.items()}
    protocol={'config':cfg,'models':manifest,'code':{name:sha256(root/name) for name in
        ('slater_mechanics_trainer.py','slater_mechanics_core.py','slater_mechanics_env.py',
         'slater_mechanics_eval.py','slater_ppo.py','slater_cycle9_native_ppo_v025.py',
         'slater_nexto_scheduler_v038b.py','afk_team_research.py','mechanics_scenarios.py',
         'nexto_teacher.py','vendor/nexto/nexto_obs.py','slater_v041_worker.py')}}
    from importlib.metadata import version
    protocol['runtime']={name:version(name) for name in ('torch','numpy','rlgym-rocket-league','rocketsim')}
    if resume:
        if read_json(run_dir/'protocol.json')!=protocol:raise RuntimeError('Run configuration/models changed')
    run_dir.mkdir(parents=True,exist_ok=True)
    with process_lock(run_dir/'trainer.lock'):
        if not resume:atomic_json(run_dir/'protocol.json',protocol)
        torch.set_num_threads(2);torch.manual_seed(cfg['seed']);np.random.seed(cfg['seed']);random.seed(cfg['seed'])
        actor=load_actor(root,source,trainable=True)
        original=load_actor(root,source)
        teacher=load_actor(root,source)
        rivals={name:load_actor(root,p) for name,p in paths.items()}
        critic=MechanicsCritic()
        ao=torch.optim.Adam(actor.parameters(),lr=cfg['actor_lr'])
        co=torch.optim.Adam(critic.parameters(),lr=cfg['critic_lr'])
        # Reward definitions/critic heads differ from match PPO; start new Adam
        # states intentionally. Only the selected actor weights are transferred.
        progress={'stage_index':0,'stage_updates':0,'total_updates':0,'decisions':0,
                  'difficulty':0.,'mastered':[],'teacher_path':str(source),
                  'trusted_path':None,'mastery_passes':0}
        if resume:
            progress=read_json(run_dir/'progress.json')
            if not progress:raise ValueError('No completed update to resume')
            cp=root/progress['latest_path'];doc=torch.load(cp,map_location='cpu',weights_only=True)
            if sha256(cp)!=progress['latest_sha']:raise RuntimeError('Saved mechanics checkpoint changed')
            actor.load_state_dict(doc['actor']);critic.load_state_dict(doc['critic'])
            ao.load_state_dict(doc['actor_optimizer']);co.load_state_dict(doc['critic_optimizer'])
            teacher=load_actor(root,Path(progress['teacher_path']))
            for group in ao.param_groups:group['lr']=cfg['actor_lr']
        if progress['stage_index']>=len(STAGES):
            print('MECHANICS_CURRICULUM_COMPLETE',flush=True);return run_dir
        start=time.perf_counter();start_decisions=progress['decisions']
        evaluation_origin=int(hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()[:12],16)*2**40
        stage_budget=1 if smoke else cfg['updates_per_stage']
        stage_limit=progress['stage_updates']+stage_budget
        remaining=updates_override or stage_budget
        envs=[]
        try:
            while remaining>0 and progress['stage_index']<len(STAGES):
                stage=STAGES[progress['stage_index']]
                if not envs:
                    for j in range(cfg['n_envs']):
                        retention=j==cfg['n_envs']-1
                        rehearsal=progress['mastered'] if cfg['n_envs']>=4 and j==cfg['n_envs']-2 else ()
                        envs.append(MechanicsEnv(rivals,stage=stage,difficulty=progress['difficulty'],
                            retention=retention,rehearsal_stages=rehearsal,
                            max_seconds=cfg['retention_seconds'] if retention else cfg['episode_seconds'],
                            anchor_weight=cfg['retention_anchor'] if retention or rehearsal else cfg['mechanic_anchor']))
                    seeds=[cfg['seed']+j*100003+progress['total_updates']*97 for j in range(len(envs))]
                    observations=[env.reset(s) for env,s in zip(envs,seeds)]
                collect_started=time.perf_counter()
                script_ticks_before=sum(e.total_script_ticks for e in envs)
                rows,finished,observations,seeds,trunc=collect_batched(
                    actor,critic,envs,observations,seeds,cfg['steps_per_env'])
                collection_seconds=time.perf_counter()-collect_started
                # Each rollout gets a fresh bounded step-size search. A rare
                # difficult batch must not permanently drive later updates to
                # a tiny learning rate. Adam moments still carry forward.
                for group in ao.param_groups:group['lr']=cfg['actor_lr']
                metric=trust_region_update(actor,teacher,critic,ao,co,rows,cfg['epochs'],
                    cfg['minibatch'],cfg['mechanic_anchor'],cfg['seed']+progress['total_updates'],
                    target_kl=cfg['target_kl'])
                progress['total_updates']+=1;progress['stage_updates']+=1
                progress['decisions']+=len(rows['action']);remaining-=1
                practice=[r for r in finished if not r['retention'] and r.get('stage',stage)==stage]
                rate=sum(r['success'] for r in practice)/len(practice) if practice else None
                # Coarse ease adjustment at episode boundaries; holdout always
                # uses full difficulty and does not inherit this training aid.
                if rate is not None and len(practice)>=4:
                    progress['difficulty']=float(np.clip(progress['difficulty']+(.1 if rate>.7 else -.05 if rate<.2 else 0),0,1))
                    for env in envs:
                        if not env.retention and not env.rehearsal_stages:env.difficulty=progress['difficulty']
                metric.update(stage=stage,update=progress['total_updates'],decisions=progress['decisions'],
                    practice_success_rate=rate,completed_episodes=len(finished),
                    timeout_bootstraps=trunc,difficulty=progress['difficulty'],
                    rollout_decisions_per_second=len(rows['action'])/max(collection_seconds,1e-6),
                    end_to_end_decisions_per_second=(progress['decisions']-start_decisions)/max(time.perf_counter()-start,1e-6),
                    opponents_script_ticks=sum(e.total_script_ticks for e in envs)-script_ticks_before)
                out=run_dir/f"update_{progress['total_updates']:06d}.pt"
                payload={'stage':'slater_mechanics','actor':actor.state_dict(),'critic':critic.state_dict(),
                    'actor_optimizer':ao.state_dict(),'critic_optimizer':co.state_dict(),
                    'global_updates':progress['total_updates'],'meta':{'nexto_sha':manifest['nexto']['sha256'],
                    'source_sha256':sha256(source),'mechanic':stage,'metrics':metric,'mastered':progress['mastered']}}
                write_checkpoint(out,payload)
                progress['latest_path']=str(out.relative_to(root));progress['latest_sha']=sha256(out)
                atomic_json(run_dir/'progress.json',progress)
                atomic_json(out.with_suffix('.json'),metric)
                print('MECHANICS_UPDATE',json.dumps(metric,sort_keys=True),flush=True)
                check=smoke or remaining==0 or progress['stage_updates']%cfg['eval_every']==0 or progress['stage_updates']>=stage_limit
                if check:
                    index=progress['total_updates'];folder=run_dir/'evaluations'/f'{index:06d}'
                    # Disjoint, bounded fresh namespaces for every update/stage.
                    # NumPy SeedSequence/Python random accept arbitrary positive
                    # integers; no old 32-bit legacy seed restriction is needed.
                    seed_base=evaluation_origin+index*524288
                    evaluation=evaluate_stage(actor,rivals,stage,seeds=1 if smoke else cfg['mastery_seeds'],
                        seed_base=seed_base,seconds=cfg['episode_seconds'])
                    ok,mastery=mastery_verdict(evaluation['records'])
                    atomic_json(folder/'mechanic.json',evaluation)
                    keep=retention_check(actor,original,rivals,seeds=1 if smoke else cfg['retention_seeds'],
                        seed_base=seed_base+6*65536,seconds=8 if smoke else cfg['retention_seconds'],
                        allowed_drop=cfg['allowed_goal_diff_drop_per_minute'])
                    atomic_json(folder/'retention.json',keep)
                    print('MECHANICS_EVAL',stage,json.dumps(mastery),
                          'retention_pass',keep['passed'],flush=True)
                    if smoke and metric['accepted_actor_epochs']==0:
                        raise RuntimeError('Smoke produced no accepted actor update; inspect policy KL/backtracking')
                    if not smoke:
                        if keep['passed']:
                            # A recoverable retained candidate is separate from
                            # source models; no overwrite of an existing file.
                            progress['trusted_path']=str(out.relative_to(root))
                        else:
                            recovery=root/progress['trusted_path'] if progress['trusted_path'] else source
                            recovered=load_actor(root,recovery)
                            actor.load_state_dict(recovered.state_dict())
                            ao=torch.optim.Adam(actor.parameters(),lr=cfg['actor_lr'])
                            progress['mastery_passes']=0
                            print('MECHANICS_RETENTION_ROLLBACK',recovery,flush=True)
                        # Two consecutive full-difficulty fresh-seed passes,
                        # each with a retention pass, are needed to advance.
                        progress['mastery_passes']=progress['mastery_passes']+1 if ok and keep['passed'] else 0
                        if progress['mastery_passes']>=2:
                            prior_ok=True
                            for previous_index,previous_stage in enumerate(progress['mastered']):
                                old_eval=evaluate_stage(actor,rivals,previous_stage,seeds=cfg['mastery_seeds'],
                                    seed_base=seed_base+(previous_index+1)*65536,seconds=cfg['episode_seconds'])
                                atomic_json(folder/f'previous_{previous_stage}.json',old_eval)
                                prior_ok &= mastery_verdict(old_eval['records'])[0]
                            if prior_ok:
                                progress['mastered'].append(stage);progress['stage_index']+=1
                                progress['stage_updates']=0;progress['difficulty']=0.;progress['mastery_passes']=0
                                progress['teacher_path']=str(out);teacher=load_actor(root,out)
                                stage_limit=stage_budget
                                print('MECHANICS_STAGE_MASTERED',stage,flush=True)
                                for env in envs:env.close()
                                envs=[]
                            else:
                                progress['mastery_passes']=0
                                print('MECHANICS_PREVIOUS_SKILL_REGRESSION',flush=True)
                        # Commit the post-evaluation state too: a rollback must
                        # not resurrect rejected actor weights on resume.
                        committed=run_dir/f"accepted_{index:06d}.pt"
                        payload['actor']=actor.state_dict();payload['actor_optimizer']=ao.state_dict()
                        write_checkpoint(committed,payload)
                        progress['latest_path']=str(committed.relative_to(root));progress['latest_sha']=sha256(committed)
                        atomic_json(run_dir/'progress.json',progress)
                        atomic_json(run_dir/'selected.json',{
                            'checkpoint':progress['trusted_path'],'mastered':progress['mastered'],
                            'status':'RETAINED_SIMULATOR_CANDIDATE_ONLY'})
                if smoke:break
                if progress['stage_updates']>=stage_limit:
                    print('MECHANICS_STAGE_BUDGET_REACHED',stage,'Not yet mastered; resume for more practice.',flush=True)
                    break
        finally:
            for env in envs:env.close()
        for entry in manifest.values():
            if sha256(entry['path'])!=entry['sha256']:raise RuntimeError('A protected input model changed')
        atomic_json(run_dir/'run_summary.json',{'new_decisions':progress['decisions']-start_decisions,
            'elapsed_seconds':time.perf_counter()-start,
            'complete_decisions_per_second':(progress['decisions']-start_decisions)/(time.perf_counter()-start),
            'mastered':progress['mastered'],'integration_smoke':smoke,
            'source_sha256':sha256(source)})
        print('MECHANICS_SMOKE_PASS' if smoke else 'MECHANICS_TRAINING_STOPPED',run_dir,flush=True)
        return run_dir


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('compare','preflight','smoke','train','resume','status'))
    p.add_argument('--config',default='slater_mechanics_config.json')
    p.add_argument('--source');p.add_argument('--selection');p.add_argument('--run')
    p.add_argument('--updates',type=int)
    p.add_argument('--candidate',action='append',help='Additional checkpoint path for model comparison')
    p.add_argument('--tournament',help='Round-robin results JSON: compare the leading native actors in full matches')
    p.add_argument('--finalists',type=int,default=3)
    p.add_argument('--candidate-rivals',action='store_true',help='Also use every candidate as a common frozen benchmark rival')
    p.add_argument('--seeds',type=int,default=8);p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--seed-base',type=int,default=510_000_000,help='Change this for an independent comparison experiment')
    p.add_argument('--out',default='data/isolated/mechanics_comparison01.json')
    a=p.parse_args(argv)
    cfg={**DEFAULT_CONFIG,**read_json(ROOT/a.config,{})}
    if a.run:cfg['run_name']=a.run
    torch.set_num_threads(2)
    if a.command=='status':
        print(json.dumps(read_json(ROOT/'data/isolated/mechanics_curriculum'/cfg['run_name']/'progress.json',{}),indent=2));return
    if a.command=='compare':
        if not 1<=a.seeds<=64 or not 8<=a.seconds<=300:p.error('Invalid comparison budget')
        if not 1<=a.seed_base<2**63:p.error('Invalid comparison seed base')
        if not 2<=a.finalists<=16:p.error('Finalists must be 2..16')
        if a.tournament and a.candidate:p.error('Use either --tournament or --candidate')
        candidates=known_candidates(ROOT)
        if a.tournament:candidates=tournament_candidates(ROOT,a.tournament,a.finalists)
        if a.candidate:
            candidates={f'candidate_{i}_{Path(path).stem}':(ROOT/path).resolve() for i,path in enumerate(a.candidate)}
        if len(candidates)<2:raise ValueError('Could not find two candidates; supply --candidate paths')
        default=(ROOT/cfg['source_checkpoint']).resolve()
        source=default if default.is_file() else next(iter(candidates.values()))
        out=base_output(ROOT,a.out)
        rival_paths=model_paths(ROOT,source,cfg)
        if a.candidate_rivals or a.tournament:
            existing={sha256(path) for path in rival_paths.values()}
            for name,path in candidates.items():
                digest=sha256(path)
                if digest not in existing:
                    rival_paths['benchmark_'+name]=path;existing.add(digest)
        compare_models(ROOT,candidates,rival_paths,seeds=a.seeds,seconds=a.seconds,out=out,seed_base=a.seed_base)
        return
    validate_config(cfg);source=select_source(ROOT,cfg,a)
    if a.command=='preflight':
        load_actor(ROOT,source,trainable=True)
        for path in model_paths(ROOT,source,cfg).values():load_actor(ROOT,path)
        print('MECHANICS_PREFLIGHT_PASS',source,'ALL_RIVALS_SCRIPTED_KICKOFF_ON',flush=True);return
    if a.updates is not None and not 1<=a.updates<=10000:p.error('Invalid update budget')
    train(ROOT,cfg,source,smoke=a.command=='smoke',resume=a.command=='resume',updates_override=a.updates)


def base_output(root,path):
    out=(root/path).resolve()
    if not out.is_relative_to((root/'data/isolated').resolve()):raise ValueError('Output must be inside data/isolated')
    return out


if __name__=='__main__':main()
