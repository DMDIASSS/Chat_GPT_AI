"""Select a tested, frozen Fusion student locally; never promote a main bot."""
from __future__ import annotations
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import zipfile
import numpy as np
import torch
from filelock import FileLock,Timeout
from .core import ROOT,atomic_json,check_model,write_model_meta,sha256
from .chronos import CHRONOS_CONTRACT
from .chronos_training import load_network,ChronosRunner
from .chronos_league import play_match,match_summary
from .chronos_guard import paired_statistics,EvaluationStopped
from .giga_teachers import GigaNetwork
from .training import load_config
from .research import stamp,run_path,provenance,LIMITS

BASE=ROOT.parent/'triadbot/fusion_selection'


def parameter_fingerprint(actor):
    digest=hashlib.sha256()
    for name,tensor in sorted(actor.state_dict().items()):
        tensor=tensor.detach().cpu().contiguous()
        digest.update(name.encode());digest.update(str((tensor.dtype,tuple(tensor.shape))).encode())
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def fusion_runs(name):
    root=(ROOT/'runs').resolve()
    runs=sorted(p for p in root.glob('fusion*') if p.is_dir()) if name=='all' else [(root/name).resolve()]
    if any(p.parent!=root for p in runs):raise ValueError('Fusion run must be a direct child of NovaForge/runs')
    runs=[p for p in runs if (p/'fusion_state.json').exists() and (p/'config.json').exists()]
    if not runs:raise FileNotFoundError('No Fusion run found. Expected NovaForge/runs/fusion01 with fusion_state.json and config.json.')
    return runs


def checkpoint_paths(run):
    paths=set((run/'checkpoints').glob('step_*.zip'))
    paths.update((run/'snapshots').glob('*.pt'))
    paths.update((run/'snapshots').glob('*.lt'))
    paths.update((run/'champions').glob('*/full.zip'))
    for record in ('champion.json','latest.json'):
        if (run/record).exists():
            path=(run/json.loads((run/record).read_text())['path']).resolve()
            if not path.is_relative_to(run.resolve()):raise ValueError('Fusion checkpoint pointer escapes its run')
            paths.add(path)
    return sorted(paths)


def source_hashes(runs):
    result={}
    for run in runs:
        files=checkpoint_paths(run)+[run/n for n in ('config.json','fusion_state.json','latest.json','champion.json','guard_state.json','status.json','league.json')]
        for p in files:
            for path in (p,Path(str(p)+'.json')):
                if path.is_file():result[str(path)]=sha256(path)
    return result


def save_frozen(actor,path,step=0,**details):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    actor=actor.cpu().eval()
    for parameter in actor.parameters():parameter.requires_grad_(False)
    torch.jit.save(torch.jit.script(actor),str(path))
    from .models import _sync_serialized_file
    _sync_serialized_file(path)
    write_model_meta(path,contract=CHRONOS_CONTRACT,timesteps=int(step),role='frozen_local_fusion_teacher',**details)


def ranking(rows,candidates):
    # Match points first, then goal difference. Ties are deterministic, not proof
    # that the tie-break winner is stronger.
    def key(name):
        s=match_summary(rows[name])
        return (-(s['wins']+.5*s['draws']),-(s['goals_for']-s['goals_against']),-s['goals_for'],name)
    return sorted(candidates,key=key)


def stage(cfg,actors,pairs,seconds,seed,stop):
    opponents=('chronos','galactus','nexto','ripple');rows={name:[] for name in actors}
    policies={name:ChronosRunner(path) for name,path in actors.items()}
    total=len(actors)*4*pairs*2;done=0
    print(f'FUSION_STAGE: {total} games at {seconds:g} simulated seconds/game',flush=True)
    for cell,opponent in enumerate(opponents):
        for pair in range(pairs):
            game_seed=seed+cell*100000+pair
            for side in (0,1):
                initial=None
                for name,policy in policies.items():
                    prefix=f'FUSION GAME {done+1}/{total} {name} vs {opponent} side={side}'
                    print(prefix+' START',flush=True)
                    def progress(event):print(prefix+f' RUNNING {event["simulated_seconds"]:.1f}/{event["seconds"]:.1f}s score={event["goals_for"]}:{event["goals_against"]}',flush=True)
                    row=play_match(cfg,policy,opponent,side,game_seed,seconds,stop,progress=progress)
                    if initial is None:initial=row['initial_observation_sha256']
                    elif row['initial_observation_sha256']!=initial:raise RuntimeError('Fusion selection starts differ')
                    rows[name].append(row);done+=1
                    print(prefix+f' DONE score={row["goals_for"]}:{row["goals_against"]}',flush=True)
    return rows


def select_best(run_name='all',pairs=1,seconds=30,confirmation_pairs=2,confirmation_seconds=60,max_candidates=12):
    for n in (pairs,confirmation_pairs):
        if not isinstance(n,int) or not 1<=n<=8:raise ValueError('Use 1..8 seed pairs')
    if any(not np.isfinite(s) or not 8/120<=s<=120 for s in (seconds,confirmation_seconds)):raise ValueError('Use 0.067..120 seconds/game')
    if max_candidates<0:raise ValueError('Candidate limit cannot be negative; zero means all')
    print('FUSION_SELECTION_START: pause Fusion and wait for saving. This tests available saved students; it does not train or change a champion.',flush=True)
    torch.set_num_threads(1)
    from .teachers import fetch_teachers,verify_teacher
    fetch_teachers(['chronos','galactus','ripple','nexto'])
    runs=fusion_runs(run_name);BASE.mkdir(parents=True,exist_ok=True)
    try:
        with FileLock(str(BASE/'selection.lock'),timeout=0),ExitStack() as stack:
            for run in runs:stack.enter_context(FileLock(str(run/'train.lock'),timeout=0))
            before=source_hashes(runs);started=time.monotonic()
            (BASE/'STOP').unlink(missing_ok=True)
            with tempfile.TemporaryDirectory(prefix='.incomplete_',dir=BASE) as tmp:
                work=Path(tmp);control=GigaNetwork(verify_teacher('chronos'),'chronos');original=parameter_fingerprint(control)
                save_frozen(control,work/'original_chronos.pt');actors={'original_chronos':work/'original_chronos.pt'}
                choices=[];skipped=[];seen={original}
                try:
                    records=[]
                    for run in runs:
                        for path in checkpoint_paths(run):
                            try:
                                meta=check_model(path,CHRONOS_CONTRACT)
                                if meta['timesteps']>0:records.append((int(meta['timesteps']),run,path,meta))
                            except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:skipped.append(dict(path=str(path.relative_to(ROOT)),reason=type(e).__name__))
                    for step,run,path,meta in sorted(records,key=lambda x:(-x[0],str(x[2]))):
                        actor=load_network(path);fingerprint=parameter_fingerprint(actor)
                        if fingerprint in seen:
                            skipped.append(dict(path=str(path.relative_to(ROOT)),reason='Same policy parameters as original Chronos or another candidate'));continue
                        seen.add(fingerprint)
                        if max_candidates and len(choices)>=max_candidates:
                            skipped.append(dict(path=str(path.relative_to(ROOT)),reason='Candidate budget; not tested'));continue
                        label=f'fusion_{len(choices)+1:02d}_{step}'
                        dst=work/label/'actor.pt'
                        save_frozen(actor,dst,step,source_checkpoint_sha256=meta['sha256'],parameter_sha256=fingerprint)
                        choices.append(dict(label=label,run=run.name,source=str(path.relative_to(ROOT)),
                            source_sha256=meta['sha256'],parameter_sha256=fingerprint,timesteps=step,
                            training_body=json.loads((run/'config.json').read_text())['env'].get('learner_hitbox','octane')))
                        actors[label]=dst
                        print('FUSION_CANDIDATE:',label,path.name,flush=True)
                    if not choices:raise RuntimeError('No distinct trained Fusion candidates remain. Original-Chronos duplicates are not added as a fourth expert.')
                    cfg=load_config(ROOT/'configs/chronos.json');cfg['env']['learner_hitbox']='breakout'
                    print(f'Candidates={len(choices)} plus original Chronos control; screening then fresh-seed confirmation. Other original files are preserved.',flush=True)
                    screening=stage(cfg,actors,pairs,seconds,371000001,BASE/'STOP')
                    order=ranking(screening,[c['label'] for c in choices]);finalists=order[:2]
                    final_actors={name:actors[name] for name in ['original_chronos']+finalists}
                    confirmation=stage(cfg,final_actors,confirmation_pairs,confirmation_seconds,391000001,BASE/'STOP')
                    confirmed_order=ranking(confirmation,finalists);winner=confirmed_order[0]
                    statistics=paired_statistics(confirmation[winner],confirmation['original_chronos'])
                    report=dict(kind='fusion_candidate_selection_v1',created=stamp(),screening_seed=371000001,confirmation_seed=391000001,
                        evaluation_body='breakout',candidates=choices,skipped=skipped,screening_ranking=order,confirmation_ranking=confirmed_order,
                        selected=next(c for c in choices if c['label']==winner),selected_actor=winner+'/actor.pt',
                        selected_actor_sha256=sha256(actors[winner]),original_parameter_sha256=original,
                        screening={k:match_summary(v) for k,v in screening.items()},confirmation={k:match_summary(v) for k,v in confirmation.items()},
                        selected_vs_original_statistics=statistics,trials=dict(screening=screening,confirmation=confirmation),
                        provenance=provenance(cfg),wall_seconds=time.monotonic()-started,
                        selection_rule='Best tested trained Fusion on fresh confirmation match points, goal difference as tie-break. Original Chronos is a separate control. Not a guarantee of the strongest possible checkpoint or a promotion.',
                        limitations=LIMITS+' Deleted/pruned checkpoints cannot be tested. Only listed candidates were tested. All candidates are evaluated on the Breakout body used by the new selector; trained bodies can differ.')
                except (KeyboardInterrupt,EvaluationStopped):
                    print('FUSION_SELECTION_CANCELLED: previous selection and all source runs retained.',flush=True);return
                finally:
                    if source_hashes(runs)!=before:raise RuntimeError('Fusion source files changed during selection')
                report['source_files_unchanged']=True;atomic_json(work/'report.json',report)
                destination=BASE/stamp();work.rename(destination)
                atomic_json(BASE/'latest.json',dict(path=destination.name,report_sha256=sha256(destination/'report.json')))
                zip_path=BASE.parent/'reports'/f'fusion_selection_{destination.name}.zip';zip_path.parent.mkdir(parents=True,exist_ok=True)
                with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:z.write(destination/'report.json','fusion_selection.json')
                print('BEST_TESTED_FUSION:',winner,'vs original',statistics,flush=True)
                print('FUSION_SELECTION_REPORT_READY:',zip_path,flush=True)
                return destination
    except Timeout as e:raise RuntimeError('Fusion training or selection is active. Pause Fusion with NovaForge launcher 44 and wait for saving; then retry.') from e


def selected_record():
    pointer=json.loads((BASE/'latest.json').read_text());selection=(BASE/pointer['path']).resolve()
    if not selection.is_relative_to(BASE.resolve()) or sha256(selection/'report.json')!=pointer['report_sha256']:raise ValueError('Invalid Fusion selection record')
    report=json.loads((selection/'report.json').read_text());actor=(selection/report['selected_actor']).resolve()
    if not actor.is_relative_to(selection) or sha256(actor)!=report['selected_actor_sha256']:raise ValueError('Selected Fusion actor changed')
    check_model(actor,CHRONOS_CONTRACT)
    if report['selected']['parameter_sha256']==report['original_parameter_sha256']:raise ValueError('Selected Fusion is original Chronos, not a distinct fourth expert')
    return pointer,report,actor


def prepare_refinement(run_name='fusion_refine01'):
    from .chronos_training import new_chronos_model,ChronosCallback
    from .chronos_guard import ensure_champion
    from .chronos import ChronosEnv
    from .tracking import Tracker
    pointer,report,actor=selected_record();run=(ROOT/'runs'/run_name).resolve()
    if run.parent!=(ROOT/'runs').resolve() or run.exists():raise ValueError('Use a new refinement run name; an existing run is resumed, never overwritten')
    run.parent.mkdir(parents=True,exist_ok=True);torch.set_num_threads(1)
    with tempfile.TemporaryDirectory(prefix='.incomplete_',dir=run.parent) as tmp:
        work=Path(tmp);cfg=load_config(ROOT/'configs/chronos.json');cfg['trainer']='chronos_ppo_v1'
        cfg['fusion_refinement']=dict(selection_report_sha256=pointer['report_sha256'],source_actor_sha256=sha256(actor),target_decisions=131072)
        cfg['chronos']['guard']['seed']=431000001
        cfg['league']['weights']={k:v*.95 for k,v in cfg['league']['weights'].items()};cfg['league']['weights']['demochaser']=.05
        env=ChronosEnv(cfg,opponent='scorer');tracker=Tracker(work,cfg,mode='off')
        try:
            model=new_chronos_model(cfg,env,initialize=False);frozen=load_network(actor)
            model.policy.actor.load_state_dict(frozen.state_dict(),strict=True)
            model.policy.anchor.load_state_dict(frozen.state_dict(),strict=True)
            atomic_json(work/'config.json',cfg)
            atomic_json(work/'provenance.json',dict(contract=CHRONOS_CONTRACT,teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),
                initialization='Best tested trained Fusion; fresh critic/optimizer, anchor frozen to selected Fusion',fusion_selection=report['selected'],
                source_actor_sha256=sha256(actor),selection_report_sha256=pointer['report_sha256']))
            atomic_json(work/'fusion_state.json',dict(phase='complete',initialization='Selected trained Fusion refinement'))
            callback=ChronosCallback(work,cfg,tracker,False);callback.init_callback(model);callback.persist(force=True);ensure_champion(work)
        finally:env.close();tracker.finish('prepared')
        work.rename(run)
    print('FUSION_REFINEMENT_READY:',run,'Fresh value warmup; frozen-opponent league plus snapshot self-play and 5% scripted demo stress.',flush=True)
    return run


def train_refinement(run_name='fusion_refine01',wandb='online'):
    from .chronos_training import train_chronos,resolve_chronos
    from types import SimpleNamespace
    run=(ROOT/'runs'/run_name).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid refinement run')
    cfg=load_config(run/'config.json');settings=cfg['fusion_refinement']
    current=check_model(resolve_chronos(run),CHRONOS_CONTRACT)['timesteps'];remaining=max(0,settings['target_decisions']-current)
    if not remaining:print('REFINEMENT_BUDGET_COMPLETE: use the retained champion for the four-expert run.',flush=True);return
    train_chronos(SimpleNamespace(run=run_name,resume=True,config=None,device=None,wandb=wandb,forever=False,steps=remaining,clear_halt=False))


def create_four(run_name='selector04',refinement='fusion_refine01',direct=False):
    with ExitStack() as locks:
        locks.enter_context(FileLock(str(BASE/'selection.lock'),timeout=0))
        if not direct:
            run=(ROOT/'runs'/refinement).resolve()
            if run.parent!=(ROOT/'runs').resolve() or not (run/'config.json').exists():raise FileNotFoundError('Prepare and train the selected Fusion refinement first')
            locks.enter_context(FileLock(str(run/'train.lock'),timeout=0))
        return _create_four(run_name,refinement,direct)


def _create_four(run_name,refinement,direct):
    from .triad_selector import FOUR_NAMES
    target=run_path(run_name)
    if target.exists():raise ValueError('Four-expert run already exists. Resume it; do not overwrite it.')
    pointer,report,actor=selected_record();refinement_source=None
    if not direct:
        from .chronos_training import resolve_chronos
        from .chronos_guard import select_checkpoint
        run=(ROOT/'runs'/refinement).resolve()
        if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid refinement run')
        cfg=load_config(run/'config.json');settings=cfg['fusion_refinement']
        if settings['selection_report_sha256']!=pointer['report_sha256']:raise ValueError('Refinement belongs to a different Fusion selection')
        from .chronos import ChronosPPO
        latest=resolve_chronos(run);model=ChronosPPO.load(latest,device='cpu')
        if model.num_timesteps<settings['target_decisions'] and not getattr(model,'training_halt_reason',None):raise RuntimeError('Finish the bounded Fusion refinement before freezing its retained champion; --direct is an explicit alternative')
        refinement_source=select_checkpoint(run)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.incomplete_',dir=target.parent) as temp:
        stage=Path(temp)
        if refinement_source:
            chosen=load_network(refinement_source)
            if parameter_fingerprint(chosen)==report['original_parameter_sha256']:raise ValueError('Refined teacher is an original-Chronos duplicate; no distinct fourth expert')
            save_frozen(chosen,stage/'frozen_fusion.pt',check_model(refinement_source,CHRONOS_CONTRACT)['timesteps'],
                source_refinement_sha256=sha256(refinement_source),selected_source_actor_sha256=sha256(actor))
            atomic_json(stage/'fusion_refinement.json',dict(run=refinement,source_sha256=sha256(refinement_source),
                selected_actor_sha256=sha256(actor),retained_champion=json.loads((run/'champion.json').read_text()),
                guard=json.loads((run/'guard_state.json').read_text()) if (run/'guard_state.json').exists() else None))
        else:
            shutil.copy2(actor,stage/'frozen_fusion.pt');shutil.copy2(str(actor)+'.json',stage/'frozen_fusion.pt.json')
        cfg=load_config(ROOT/'configs/chronos.json');cfg.update(workers=1,threads=1,device='cpu',selector_experts=list(FOUR_NAMES))
        cfg['selector_opponents']={n:.2375 for n in ('chronos','galactus','ripple','nexto')};cfg['selector_opponents']['demochaser']=.05
        cfg['league']['weights']=dict(cfg['selector_opponents'])
        cfg['env']['learner_hitbox']='breakout';cfg['fusion_teacher']=dict(path='frozen_fusion.pt',sha256=sha256(stage/'frozen_fusion.pt'))
        atomic_json(stage/'config.json',cfg);atomic_json(stage/'fusion_selection.json',report)
        stage.rename(target)
    print('FOUR_EXPERT_RUN_READY:',target,'Start the separate training launcher; selector01 is unchanged.',flush=True)
    return target
