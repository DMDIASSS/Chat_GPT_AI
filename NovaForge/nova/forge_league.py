"""Serial, checkpointed research league. Deployment pointers change after evidence.

No incumbent selector/Fusion run is modified. Full optimizers, immutable task
recipes, frozen opponents, reward definitions and source hashes are retained.
"""
from __future__ import annotations

import copy
import gc
import json
import math
from pathlib import Path
import random
import re
import shutil
import time
import uuid
import zipfile

from filelock import FileLock
import numpy as np
import torch
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure

from .chronos import CHRONOS_CONTRACT, ChronosPPO
from .core import ROOT, atomic_json, check_model, sha256
from .forge_env import ForgeEnv, PROFILES
from .forge_eval import Stopped, suite, judgement, summary
from .forge_models import FAMILIES, DirectActor, GigaNetwork, contract, new_model, save_actor
from .models import save_ppo
from .teachers import fetch_teachers, verify_teacher
from .tracking import Tracker

PROJECT=ROOT.parent/'forgeleague'


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def run_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):raise ValueError('Use a simple run name, no path separators')
    # Windows temp/profile paths may use an 8.3 alias (RUNNER~1). Keep the
    # run and every resolved artifact in the same canonical namespace.
    return (PROJECT/'runs'/name).resolve()


def validate(cfg):
    if cfg['version']!='forgeleague-v1':raise ValueError('Unknown league version')
    p=cfg['ppo'];rollout=p['n_steps']
    for k in ('pilot_decisions','block_decisions','checkpoint_decisions','specialist_decisions'):
        if not isinstance(cfg[k],int) or cfg[k]<rollout or cfg[k]%rollout:raise ValueError(k+' must be a positive multiple of n_steps')
    if rollout<2 or not 1<p['batch_size']<=rollout or rollout%p['batch_size']:raise ValueError('Invalid rollout/minibatch size')
    if cfg['device'] not in ('cpu','cuda','auto'):raise ValueError('Invalid device')
    if not 0<p['gamma']<=1 or cfg['threads']<1 or cfg['match_seconds']<=0:raise ValueError('Invalid training settings')
    for key in ('actor_lr','critic_lr','anchor_kl_limit'):
        if not math.isfinite(cfg[key]) or cfg[key]<=0:raise ValueError('Invalid '+key)
    if cfg['anchor_coef']<0 or cfg['warmup_rollouts']<0 or cfg['checkpoint_keep']<1:raise ValueError('Invalid protection settings')
    objective=cfg['objective']
    if objective['version']!='timed-match-goal-potential-v1':raise ValueError('Unknown reward revision')
    if any(not math.isfinite(objective[k]) or objective[k]<0 for k in ('goal','match_result','field','distance')):raise ValueError('Invalid reward coefficient')
    if not 0<objective['goal']<=100 or objective['match_result']>100 or max(objective['field'],objective['distance'])>1:raise ValueError('Reward bound exceeded')
    if cfg['specialists_per_cycle'] not in (0,2) or cfg['max_history_per_family']<1:raise ValueError('Invalid league size')
    if not cfg['specialist_profiles'] or any(k not in PROFILES for k in cfg['specialist_profiles']):raise ValueError('Unknown specialist profile')
    e=cfg['evaluation']
    if min(e['pairs'],e['confirmation_pairs'],e['test_pairs'])<1 or min(e['seconds'],e['test_seconds'])<=0:raise ValueError('Invalid evaluation budget')
    s=cfg['opponent_sampling']
    if not .25<=s['uniform_fraction']<=1 or not 1<=s['max_weight_ratio']<=5:raise ValueError('Invalid opponent sampling bounds')
    return cfg


def entry(path,name=None):
    path=Path(path).resolve();meta=read(str(path)+'.json');check_model(path,contract(meta['contract']['family']))
    return dict(name=name or meta['contract']['family'],family=meta['contract']['family'],path=str(path),sha256=meta['sha256'])


def local(run,path):
    target=(Path(run)/path).resolve()
    if not target.is_relative_to(Path(run).resolve()):raise ValueError('Artifact escapes its run')
    return target


def champion(run,family):return local(run,read(Path(run)/f'champions/{family}.json')['actor'])


def auto_fusion():
    for selector in ('selector06','selector04'):
        root=ROOT.parent/'triadbot/runs'/selector
        if (root/'config.json').exists():
            spec=read(root/'config.json').get('fusion_teacher')
            if spec:
                from .triad_selector import fusion_asset
                path=fusion_asset(root,spec) # refuse corrupt existing assets
                check_model(path,CHRONOS_CONTRACT)
                return path
    return None


def create(name='duel01',config=None,fusion=None):
    run=run_path(name)
    if run.exists():
        if (run/'state.json').exists():
            print('FORGE_EXISTS: keeping existing run; use 2_START_OR_RESUME.',flush=True);return run
        raise FileExistsError('Incomplete run exists; choose a new run name to preserve it')
    cfg=validate(read(config or ROOT/'configs/forge_league.json'));torch.set_num_threads(cfg['threads'])
    fetch_teachers(['chronos','galactus','nexto','ripple'])
    source=Path(fusion).resolve() if fusion else auto_fusion()
    if source:check_model(source,CHRONOS_CONTRACT)
    run.parent.mkdir(parents=True,exist_ok=True)
    stage=run.parent/(name+'.creating-'+uuid.uuid4().hex[:8]);stage.mkdir()
    try:
        atomic_json(stage/'config.json',cfg)
        lineage={}
        for index,family in enumerate(FAMILIES):
            torch.manual_seed(cfg['seed']+index)
            actor=DirectActor(family)
            native=GigaNetwork(verify_teacher(family),family)
            origin=dict(kind='pinned-public-native',family=family,teacher_lock=sha256(ROOT/'teachers.lock.json'))
            if family=='chronos' and source:
                native.load_state_dict(torch.jit.load(str(source),map_location='cpu').state_dict(),strict=True)
                origin=dict(kind='selected-frozen-local-Fusion',sha256=sha256(source),file_name=source.name)
            actor.core.load_state_dict(native.state_dict(),strict=True)
            save_actor(actor,stage/f'parents/{family}.lt',family,timesteps=0,origin=origin)
            lineage[family]=origin
            atomic_json(stage/f'champions/{family}.json',dict(actor=f'parents/{family}.lt',checkpoint=None,
                reason='Retained initialization; no measured improvement yet',promotions=0))
            del actor,native
        sources={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'nova').glob('*.py'))}
        atomic_json(stage/'provenance.json',dict(lineage=lineage,config_sha256=sha256(stage/'config.json'),sources=sources,
            reward_equation='goal*goal_difference + match_result*sign(final_score) + gamma*Phi(next)-Phi(old)',
            potential='field*team_relative_ball_y/5120-distance*min(car_ball_distance,12000)/6000',
            terminal_potential=0,decision_clock='8 ticks; 7 held then 1 planned; RocketSim adds one tick',
            notes=['Only actor parameters improve controls. Critics are not exported.',
                'Finite horizon; no overtime or goal pauses; both learners use Octane.',
                'After an early goal, the unused ticks of that decision are treated as dead time.',
                'Resume preserves optimizer and completed rollouts but starts a deterministically seeded new match.']))
        with zipfile.ZipFile(stage/'source.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for relative in sources:archive.write(ROOT/relative,relative)
            archive.write(stage/'config.json','config.json')
            for filename in ('requirements.txt','teachers.lock.json','THIRD_PARTY.md'):archive.write(ROOT/filename,filename)
        atomic_json(stage/'state.json',dict(version=1,phase='pilot',cycle=0,queue=[],done=[],active=None,
            selected_critic={},development={},history=[],total_decisions=0,status='ready',halt_reason=None))
        atomic_json(stage/'status.json',dict(state='ready',phase='pilot',total_decisions=0))
        stage.replace(run)
    except BaseException:
        # Preserve an interrupted creation, never overwrite a user run.
        raise
    print('FORGE_CREATED:',run,'Chronos initialization:',lineage['chronos']['kind'],flush=True)
    return run


def fork(source,name,config=None):
    """New experiment from both retained actors, with fresh critics/optimizers."""
    from .core import write_model_meta
    old=run_path(source);new=run_path(name)
    if new.exists():raise FileExistsError('Choose a new run name; a fork never overwrites runs')
    with FileLock(str(old/'train.lock'),timeout=0):
        parents={f:champion(old,f) for f in FAMILIES}
        create(name,config)
        provenance=read(new/'provenance.json')
        for family,path in parents.items():
            target=new/f'parents/{family}.lt';shutil.copy2(path,target)
            origin=dict(kind='retained-Forge-actor',source_run=source,sha256=sha256(path),
                source_lineage=read(old/'provenance.json')['lineage'][family])
            write_model_meta(target,contract=contract(family),timesteps=0,origin=origin)
            provenance['lineage'][family]=origin
        provenance['fork']=dict(source_run=source,reason='Fresh critic/optimizer and new versioned experiment; both retained actors copied exactly')
        atomic_json(new/'provenance.json',provenance)
    print('FORGE_FORK_CREATED:',new,flush=True);return new


def panel(run):return [entry(Path(run)/f'parents/{f}.lt','parent_'+f) for f in FAMILIES]+[dict(name='nexto')]


def weighted_pool(run,state,cfg):
    pool=[entry(champion(run,f),'main_'+f) for f in FAMILIES]
    pool += [dict(name=n) for n in ('chronos','galactus','nexto')]
    pool += [entry(local(run,h['actor']),h['name']) for h in state['history']]
    scores={}
    for f in FAMILIES:
        path=Path(run)/f'latest_evaluation_{f}.json'
        if path.exists():
            for row in read(path)['trials']:
                # Score concession is kept distinct from match losses.
                scores.setdefault(row['opponent'],[]).append(.7*int(row['outcome']<0)+.3*(row['goals_against']/(1+row['goals_for']+row['goals_against'])))
    raw=np.array([.1+np.mean(scores.get(e['name'].replace('main_','parent_'),[.5])) for e in pool])
    raw=np.minimum(raw,raw.min()*cfg['opponent_sampling']['max_weight_ratio'])
    u=cfg['opponent_sampling']['uniform_fraction'];prob=u/len(pool)+(1-u)*raw/raw.sum()
    for e,w in zip(pool,prob):e['weight']=float(w)
    return pool


def task_recipe(run,state,cfg,task_id,family,kind,privileged=False,profile='balanced',inherit=None,pool=None):
    recipe=dict(id=task_id,family=family,kind=kind,privileged=privileged,profile=profile,
        cycle=state['cycle'],seed=cfg['seed']+len(state['done'])*100003+len(state['queue'])*31,
        initial_actor=str(champion(run,family)),initial_sha256=sha256(champion(run,family)),
        inherit=inherit,pool=pool or panel(run),
        budget=cfg['pilot_decisions'] if kind=='pilot' else (cfg['specialist_decisions'] if kind=='specialist' else cfg['block_decisions']))
    if inherit:recipe['inherit_checkpoint_sha256']=sha256(local(run,inherit['checkpoint']))
    if kind=='pilot':recipe['seed']=cfg['seed']+FAMILIES.index(family)*100003 # paired arms
    target=Path(run)/'tasks'/task_id/'recipe.json'
    if target.exists():raise FileExistsError('Task identity collision')
    atomic_json(target,recipe);state['queue'].append(task_id)


def generate_tasks(run,state,cfg):
    if state['phase']=='pilot':
        for family in FAMILIES:
            for privileged in (False,True):
                task_recipe(run,state,cfg,'pilot_'+family+('_private' if privileged else '_control'),family,'pilot',privileged)
        return
    pool=weighted_pool(run,state,cfg);cycle=state['cycle']
    for family in FAMILIES:
        task_recipe(run,state,cfg,f'cycle{cycle:04d}_{family}',family,'main',state['selected_critic'][family],
            inherit=state['development'].get(family),pool=pool)
    if cfg['specialists_per_cycle']:
        profile=cfg['specialist_profiles'][(cycle-1)%len(cfg['specialist_profiles'])]
        for family in FAMILIES:
            task_recipe(run,state,cfg,f'cycle{cycle:04d}_{family}_{profile}',family,'specialist',False,profile=profile,pool=pool)


def _progress(task):return read(task/'progress.json') if (task/'progress.json').exists() else dict(steps=0)


def _save_generation(model,task,recipe,steps,cfg):
    generation=task/'checkpoints'/f'{steps:012d}'
    checkpoint=generation.with_suffix('.zip');actor=generation.with_suffix('.lt')
    model.forge_rng=dict(torch=torch.get_rng_state(),numpy=np.random.get_state(),python=random.getstate())
    save_ppo(model,checkpoint,contract=contract(recipe['family']),task=recipe['id'],task_steps=steps,recipe_sha256=sha256(task/'recipe.json'))
    save_actor(model.policy.actor,actor,recipe['family'],timesteps=int(model.num_timesteps),task=recipe['id'])
    progress=dict(steps=steps,checkpoint=str(checkpoint.relative_to(task)),actor=str(actor.relative_to(task)),
        actor_sha256=sha256(actor),critic_updates=model.chronos_updates)
    atomic_json(task/'progress.json',progress)
    return progress


def prune_intermediate_generations(run,state,cfg):
    """Keep the final generations and every checkpoint referenced by lineage.

    Only this new project's disposable intermediate generations are removed.
    Parents, task recipes, final actors, referenced optimizer states, completed
    evaluations and the user's existing projects are never touched.
    """
    run=Path(run);protected=set()
    def protect(path):
        if path:protected.add(Path(path).resolve())
    for p in (run/'champions').glob('*.json'):
        record=read(p)
        for key in ('actor','checkpoint'):
            if record.get(key):protect(local(run,record[key]))
    for record in state['development'].values():
        for key in ('actor','checkpoint'):protect(local(run,record[key]))
    for h in state['history']:protect(local(run,h['actor']))
    for p in (run/'tasks').glob('*/recipe.json'):
        recipe=read(p);protect(recipe['initial_actor'])
        for e in recipe['pool']:protect(e.get('path'))
        if recipe['inherit']:
            for key in ('actor','checkpoint'):protect(local(run,recipe['inherit'][key]))
    for task in (run/'tasks').iterdir():
        checkpoints=sorted((task/'checkpoints').glob('*.zip'))
        for p in checkpoints[:-cfg['checkpoint_keep']]:
            actor=p.with_suffix('.lt')
            if p.resolve() in protected or actor.resolve() in protected:continue
            for target in (p,Path(str(p)+'.json'),actor,Path(str(actor)+'.json')):target.unlink(missing_ok=True)


def _train_task(run,state,cfg,task_id,tracker):
    task=Path(run)/'tasks'/task_id;recipe=read(task/'recipe.json');progress=_progress(task)
    if progress['steps']>=recipe['budget']:return progress
    if sha256(recipe['initial_actor'])!=recipe['initial_sha256']:raise ValueError('Task parent changed')
    task_cfg=copy.deepcopy(cfg);task_cfg['seed']=recipe['seed']
    env=ForgeEnv(task_cfg,recipe['family'],recipe['pool'],profile=recipe['profile'])
    start=time.monotonic();base_steps=progress['steps'];session_start_steps=base_steps;last_log=start
    model=None;callback=None
    try:
        source=local(task,progress['checkpoint']) if progress['steps'] else (local(run,recipe['inherit']['checkpoint']) if recipe['inherit'] else None)
        if source:
            meta=check_model(source,contract(recipe['family']))
            if progress['steps'] and meta['recipe_sha256']!=sha256(task/'recipe.json'):raise ValueError('Task recipe changed after checkpointing')
            if not progress['steps'] and recipe['inherit'] and meta['sha256']!=recipe['inherit_checkpoint_sha256']:raise ValueError('Inherited optimizer checkpoint changed')
            model=ChronosPPO.load(source,env=env,device=cfg['device'])
            if model.policy.family!=recipe['family'] or model.policy.privileged!=recipe['privileged']:raise ValueError('Model/recipe mismatch')
            model.set_random_seed(recipe['seed']+progress['steps']*17)
            retained=read(Path(run)/f'champions/{recipe["family"]}.json')
            if not progress['steps'] and retained.get('checkpoint') and source==local(run,retained['checkpoint']):
                # Move the trust region only after a verified promotion. The
                # original parents remain frozen evaluation references.
                model.policy.anchor.load_state_dict(model.policy.actor.state_dict(),strict=True)
            if progress['steps'] and hasattr(model,'forge_rng'):
                torch.set_rng_state(model.forge_rng['torch']);np.random.set_state(model.forge_rng['numpy']);random.setstate(model.forge_rng['python'])
        else:model=new_model(task_cfg,env,recipe['family'],recipe['privileged'],recipe['initial_actor'])
        logdir=task/'logs';logdir.mkdir(exist_ok=True)
        # Separate CSV on every resume: no silent header loss or timestep rewind.
        model.set_logger(configure(str(logdir/str(time.time_ns())),['csv']))
        start_timestep=int(model.num_timesteps)-progress['steps']
        class Metrics(BaseCallback):
            def _on_step(self):
                nonlocal last_log
                for info in self.locals.get('infos',[]):
                    if 'episode' in info:
                        values={f'{recipe["family"]}/training/{k}':v for k,v in info.items() if k in ('outcome','goals_for','goals_against','touches')}
                        values.update({f'{recipe["family"]}/reward/{k}':v for k,v in info['reward_parts'].items()})
                        tracker.log(values,state['total_decisions']+self.num_timesteps-start_timestep-base_steps)
                if time.monotonic()-last_log>=5:
                    print(f'TRAIN {task_id}: {self.num_timesteps-start_timestep}/{recipe["budget"]} decisions; score {env.goals_for}:{env.goals_against}',flush=True)
                    last_log=time.monotonic()
                return True # stop only after a complete rollout
        callback=Metrics()
        print(f'FORGE_TRAIN {task_id}: {progress["steps"]}/{recipe["budget"]}, critic={"private" if recipe["privileged"] else "ordinary"}, fixed opponents={len(recipe["pool"])}',flush=True)
        while progress['steps']<recipe['budget']:
            if (Path(run)/'STOP').exists():raise Stopped()
            model.learn(cfg['ppo']['n_steps'],reset_num_timesteps=False,callback=callback)
            steps=int(model.num_timesteps)-start_timestep
            tracker.log({recipe['family']+'/'+k:v for k,v in model.logger.name_to_value.items() if k.startswith('train/')},
                state['total_decisions']+steps-base_steps)
            if (steps%cfg['checkpoint_decisions']==0 or steps>=recipe['budget'] or
                    (Path(run)/'STOP').exists() or getattr(model,'training_halt_reason',None)):
                progress=_save_generation(model,task,recipe,steps,cfg)
                advanced=steps-base_steps;state['total_decisions']+=advanced;base_steps=steps
                tracker.log({f'{recipe["family"]}/decisions':model.num_timesteps,'throughput/task_decisions_per_second':(steps-session_start_steps)/max(time.monotonic()-start,1e-6),
                    'league/cycle':state['cycle'],'league/critic_private':int(recipe['privileged']),
                    'train/actor_lr':model.actor_lr,'train/anchor_coef':model.anchor_coef},state['total_decisions'])
                atomic_json(Path(run)/'state.json',state)
                atomic_json(Path(run)/'status.json',dict(state='training',task=task_id,steps=steps,budget=recipe['budget'],
                    total_decisions=state['total_decisions'],seconds=time.monotonic()-start,wandb=tracker.status()))
                print(f'FORGE_SAVED {task_id}: {steps}/{recipe["budget"]}',flush=True)
                if getattr(model,'training_halt_reason',None):raise RuntimeError(model.training_halt_reason)
        return progress
    finally:
        try:
            if model is not None and hasattr(model,'_logger'):model.logger.close()
        finally:
            # SB3 callback locals can retain a reference cycle to the model.
            if callback is not None:callback.locals={};callback.model=None
            env.close();del model;gc.collect()


def log_evaluation(tracker,state,family,report,kind):
    if tracker is None:return
    values={f'{family}/{kind}/{k}':v for k,v in report['summary'].items()}
    values.update({f'{family}/{kind}/paired_{k}':v for k,v in report['statistics'].items() if isinstance(v,(float,int))})
    for opponent in {r['opponent'] for r in report['trials']}:
        group=[r for r in report['trials'] if r['opponent']==opponent]
        values.update({f'{family}/{kind}/{opponent}/{k}':v for k,v in summary(group).items()})
    tracker.log(values,state['total_decisions'])


def _guard(run,state,cfg,family,actor,checkpoint,cycle,tag,tracker=None):
    reference=champion(run,family);settings=cfg['evaluation'];root=Path(run)/'evaluations'
    atomic_json(Path(run)/'status.json',dict(state='evaluating',stage=tag,family=family,total_decisions=state['total_decisions']))
    development=suite(cfg,family,actor,reference,panel(run),'development',cycle,Path(run)/'STOP',output=root/(tag+'_dev.json'))
    log_evaluation(tracker,state,family,development,'development')
    atomic_json(Path(run)/f'latest_evaluation_{family}.json',development)
    decision=judgement(development['statistics'],settings)
    if decision=='improved':
        confirmation=suite(cfg,family,actor,reference,panel(run),'confirmation',cycle,Path(run)/'STOP',
            pairs=settings['confirmation_pairs'],output=root/(tag+'_confirm.json'))
        log_evaluation(tracker,state,family,confirmation,'confirmation')
        decision=judgement(confirmation['statistics'],settings)
    if decision=='improved':
        previous=read(Path(run)/f'champions/{family}.json')
        atomic_json(Path(run)/f'champions/{family}.json',dict(actor=str(Path(actor).relative_to(run)),
            checkpoint=str(Path(checkpoint).relative_to(run)),promotions=previous['promotions']+1,
            reason='Paired development improvement confirmed with fresh seeds',evaluation=tag))
    elif decision=='regressed':
        state['halt_reason']=f'{family} regressed against the retained champion. Latest candidate preserved; deployment unchanged.'
    print(f'FORGE_GUARD {family}: {decision}; exported champion {"updated" if decision=="improved" else "retained"}',flush=True)
    return decision


def _finish_pilot(run,state,cfg,tracker=None):
    for family in FAMILIES:
        if family in state['selected_critic']:continue
        tasks={arm:Path(run)/'tasks'/('pilot_'+family+'_'+arm) for arm in ('control','private')}
        p={arm:_progress(task) for arm,task in tasks.items()}
        actors={arm:local(tasks[arm],p[arm]['actor']) for arm in tasks}
        report=suite(cfg,family,actors['private'],actors['control'],panel(run),'development',0,Path(run)/'STOP',
            output=Path(run)/f'evaluations/pilot_{family}_critic_dev.json')
        log_evaluation(tracker,state,family,report,'critic_pilot')
        use_private=judgement(report['statistics'],cfg['evaluation'])=='improved'
        if use_private:
            report=suite(cfg,family,actors['private'],actors['control'],panel(run),'confirmation',0,Path(run)/'STOP',
                pairs=cfg['evaluation']['confirmation_pairs'],output=Path(run)/f'evaluations/pilot_{family}_critic_confirm.json')
            use_private=judgement(report['statistics'],cfg['evaluation'])=='improved'
        chosen='private' if use_private else 'control';task=tasks[chosen]
        checkpoint=local(task,p[chosen]['checkpoint'])
        _guard(run,state,cfg,family,actors[chosen],checkpoint,0,'pilot_'+family+'_parent',tracker)
        state['selected_critic'][family]=use_private
        state['development'][family]=dict(checkpoint=str(checkpoint.relative_to(run)),actor=str(actors[chosen].relative_to(run)))
        atomic_json(Path(run)/'state.json',state)
        print('FORGE_PILOT_CHOICE',family,chosen,'(ordinary wins ties/uncertainty)',flush=True)
        if state['halt_reason']:return
    state.update(phase='league',cycle=1,queue=[])


def run(name='duel01',*,wandb='online',once=False,max_tasks=None):
    path=run_path(name)
    if not (path/'state.json').exists():create(name)
    cfg=validate(read(path/'config.json'));torch.set_num_threads(cfg['threads'])
    if sha256(path/'config.json')!=read(path/'provenance.json')['config_sha256']:raise ValueError('Run config changed: create a new experiment instead')
    with FileLock(str(path/'train.lock'),timeout=0):
        state=read(path/'state.json')
        state['total_decisions']=sum(_progress(path/'tasks'/t)['steps'] for t in state['done']+state['queue'])
        if state['halt_reason']:raise RuntimeError(state['halt_reason']+' Review reports and create a new run; no automatic restart.')
        (path/'STOP').unlink(missing_ok=True)
        session=dict(id=str(time.time_ns()),source_hashes={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/'nova').glob('*.py'))})
        atomic_json(path/'sessions'/(session['id']+'.json'),session)
        tracker=Tracker(path,cfg,mode=wandb,continuous=not once)
        completed=0;status='paused'
        try:
            while True:
                if state['halt_reason']:raise Stopped()
                if (path/'STOP').exists():raise Stopped()
                if not state['queue']:
                    if state.get('batch_generated',False):
                        if state['phase']=='pilot':_finish_pilot(path,state,cfg,tracker)
                        else:state['cycle']+=1
                        state['batch_generated']=False
                        atomic_json(path/'state.json',state)
                        prune_intermediate_generations(path,state,cfg)
                        from .forge_export import export
                        exported=export(name)
                        atomic_json(path/'last_exports.json',dict(paths=[str(p) for p in exported]))
                        report(name)
                        if state['halt_reason']:raise Stopped()
                        if once:return
                    generate_tasks(path,state,cfg);state['batch_generated']=True
                atomic_json(path/'state.json',state)
                while state['queue']:
                    task_id=state['queue'][0];state['active']=task_id
                    atomic_json(path/'state.json',state)
                    progress=_train_task(path,state,cfg,task_id,tracker)
                    recipe=read(path/'tasks'/task_id/'recipe.json');family=recipe['family']
                    task=path/'tasks'/task_id;actor=local(task,progress['actor']);checkpoint=local(task,progress['checkpoint'])
                    if recipe['kind']=='main':
                        _guard(path,state,cfg,family,actor,checkpoint,state['cycle'],task_id,tracker)
                        state['development'][family]=dict(checkpoint=str(checkpoint.relative_to(path)),actor=str(actor.relative_to(path)))
                    elif recipe['kind']=='specialist':
                        state['history'].append(dict(actor=str(actor.relative_to(path)),family=family,name=task_id,
                            role='Frozen curriculum-trained challenger; not a deployment champion'))
                        keep=cfg['max_history_per_family']
                        state['history']=[h for h in state['history'] if h['family']!=family]+[h for h in state['history'] if h['family']==family][-keep:]
                    state['queue'].pop(0);state['done'].append(task_id);state['active']=None
                    state['total_decisions']=sum(_progress(path/'tasks'/t)['steps'] for t in state['done']+state['queue'])
                    atomic_json(path/'state.json',state);completed+=1
                    if state['halt_reason']:raise Stopped()
                    if max_tasks is not None and completed>=max_tasks:return
        except (Stopped,KeyboardInterrupt):pass
        except BaseException as error:
            status='error';state['halt_reason']=str(error);raise
        finally:
            if state['halt_reason']:status='halted'
            state['status']=status;atomic_json(path/'state.json',state)
            atomic_json(path/'status.json',dict(state=status,total_decisions=state['total_decisions'],
                task=state['active'],reason=state['halt_reason'],wandb=tracker.status()))
            tracker.finish(status);report(name)


def pause(name):
    path=run_path(name)
    if not (path/'state.json').exists():raise FileNotFoundError('Create the league first')
    (path/'STOP').touch();print('FORGE_PAUSE: will stop after the current rollout/save, or immediately during evaluation.',flush=True)


def report(name):
    path=run_path(name);state=read(path/'state.json')
    destination=PROJECT/'reports'/f'{name}_{time.time_ns()}.zip';destination.parent.mkdir(parents=True,exist_ok=True)
    allowed=['state.json','config.json','provenance.json','status.json','wandb_status.json']
    files=[path/f for f in allowed if (path/f).exists()]
    files+=list((path/'champions').glob('*.json'))+list((path/'evaluations').glob('*.json'))+list((path/'sessions').glob('*.json'))
    files+=list((path/'tasks').glob('*/recipe.json'))+list((path/'tasks').glob('*/progress.json'))
    files+=list((path/'tasks').glob('*/logs/*/*.csv'))
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(files):archive.write(p,p.relative_to(path).as_posix())
        archive.writestr('README.txt','Research report only. No credentials, source models or user files. W/D/L describes simulator trials, not live RLBot rank.\n')
    atomic_json(path/'last_report.json',dict(path=str(destination),total_decisions=state['total_decisions']))
    print('FORGE_REPORT:',destination,flush=True);return destination
