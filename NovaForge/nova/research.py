"""Small experiment/provenance tools. No autonomous reward tuning or promotion."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import uuid
import zipfile
from filelock import FileLock
from .core import ROOT,atomic_json,check_model,sha256
from .objectives import REGISTRY,definition

SEED_BANKS={'development':29100001,'validation':129100001,'test':229100001}
LIMITS=('Seeded starts and policy RNG do not guarantee bitwise RocketSim trajectories. '
        'Automatic demolition respawns use native randomness without an exposed global seed. '
        'Resume restores policy/optimizer/timesteps, not a mid-rollout physics/RNG snapshot. '
        'Repeat independent seeds and training seeds before claiming an improvement.')


def stamp():return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_UTC_')+uuid.uuid4().hex[:8]


def run_path(name):
    from .triad_selector import RUNS
    path=(RUNS/name).resolve()
    if path.parent!=RUNS.resolve():raise ValueError('Use a single experiment run name')
    return path


def provenance(cfg):
    from .triad_selector import TRAINING_SETTINGS
    # Keep exact project source for replaying a run after an update. No assets,
    # private logs, environment files or user checkpoints enter this archive.
    files=sorted(list((ROOT/'nova').glob('*.py'))+list((ROOT/'configs').glob('*.json'))+
        [ROOT/n for n in ('run.py','requirements.txt','teachers.lock.json','extra_teachers.lock.json')])
    digests={p.relative_to(ROOT).as_posix():sha256(p) for p in files}
    code=hashlib.sha256(json.dumps(digests,sort_keys=True).encode()).hexdigest()
    versions={}
    for name in ('torch','numpy','RocketSim','rlgym','rlgym-tools','stable-baselines3','onnxruntime'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]='unavailable'
    return dict(source_sha256=code,files=digests,versions=versions,python=platform.python_version(),
        platform=platform.platform(),teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),
        selector_training=dict(TRAINING_SETTINGS,gamma=cfg['ppo']['gamma'],workers=1,device='cpu',threads=1,
            net_arch=dict(pi=[128,128],vf=[128,128])),
        objective=definition(cfg),limitations=LIMITS)


def save_source(run,info):
    archive=Path(run)/'research/source'/f'{info["source_sha256"]}.zip'
    if not archive.exists():
        archive.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name in info['files']:z.write(ROOT/name,name)


def session(run,cfg,step):
    """Freeze configuration on first adoption; source upgrades get new sessions."""
    run=Path(run);identity=dict(config=cfg,objective=definition(cfg))
    path=run/'experiment.json'
    if path.exists():
        old=json.loads(path.read_text())
        if old['identity']!=identity:raise ValueError('Experiment configuration changed. Use research-fork for a separate run.')
    else:
        atomic_json(path,dict(schema='novaforge-experiment-v1',created=stamp(),
            adopted_at_timesteps=int(step),identity=identity))
    info=provenance(cfg);save_source(run,info)
    info.update(start_timesteps=int(step),seed=(int(cfg.get('selector_seed',271))+int(step))%2**32,session_id=stamp())
    atomic_json(run/'research/sessions'/f'{info["session_id"]}.json',info)
    return info


def bundle(run,parent):
    """Called under the run lock. Commit a complete verified backup atomically."""
    from .triad_selector import selector_meta,fusion_asset
    run=Path(run);parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
    stage=parent/('.incomplete_'+stamp());stage.mkdir()
    try:
        files=[]
        for name in ('full.zip','latest.pt','initial.pt','champion.pt'):
            if name=='full.zip' and not (run/name).exists():continue
            meta=selector_meta(run/name)
            files.extend((name,name+'.json'))
        meta=selector_meta(run/'latest.pt')
        if 'fusion_teacher' in meta:
            actor=fusion_asset(run,meta['fusion_teacher']);name=actor.relative_to(run.resolve()).as_posix()
            files.extend((name,name+'.json'))
        files+=['config.json']
        files += [n for n in ('experiment.json','guard.json','status.json','fork.json','fusion_selection.json','fusion_refinement.json','six_origin.json') if (run/n).exists()]
        for name in files:
            (stage/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(run/name,stage/name)
        record=dict(schema='novaforge-checkpoint-bundle-v1',files={n:sha256(stage/n) for n in files})
        atomic_json(stage/'bundle.json',record)
        destination=parent/stamp();stage.rename(destination)
        return destination
    finally:
        if stage.exists():shutil.rmtree(stage)


def backup(name='selector01'):
    run=run_path(name)
    if not (run/'config.json').exists():raise FileNotFoundError('No saved selector run to back up')
    with FileLock(str(run/'train.lock'),timeout=0):
        out=bundle(run,run/'backups')
    print('CHECKPOINT_BACKUP_READY:',out,flush=True)
    return out


def fork(source,name,objective_name='current',seed=271):
    """Clone a saved optimizer and latest actor into an isolated ablation run."""
    from .triad_selector import selector_meta,fusion_asset
    src=run_path(source);dst=run_path(name)
    if objective_name not in REGISTRY:raise ValueError('Unknown registered objective')
    if not 0<=seed<2**32:raise ValueError('Seed must be in 0..4294967295')
    if src==dst or dst.exists():raise ValueError('Destination run must be new; source cannot be overwritten')
    if not src.is_dir():raise FileNotFoundError('Source selector run is missing')
    with FileLock(str(src/'train.lock'),timeout=0):
        if dst.exists():raise ValueError('Destination run already exists')
        full=selector_meta(src/'full.zip');actor=selector_meta(src/'latest.pt')
        if full['timesteps']!=actor['timesteps']:raise ValueError('Full checkpoint and latest actor are from different steps')
        cfg=json.loads((src/'config.json').read_text());cfg['objective']=dict(REGISTRY[objective_name]);cfg['selector_seed']=int(seed)
        cfg['env'].setdefault('learner_hitbox','breakout')
        # These forks are selector experiments with a single simulator worker.
        cfg.update(workers=1,threads=1,device='cpu');cfg['rewards']='shaped'
        cfg['league']['weights']=dict(cfg.get('selector_opponents',{n:.25 for n in ('chronos','galactus','ripple','nexto')}))
        stage=dst.parent/('.incomplete_'+stamp());stage.mkdir()
        try:
            for n in ('full.zip','latest.pt'):
                for suffix in ('','.json'):shutil.copy2(src/(n+suffix),stage/(n+suffix))
            for n in ('initial.pt','champion.pt'):
                for suffix in ('','.json'):shutil.copy2(src/('latest.pt'+suffix),stage/(n+suffix))
            if 'fusion_teacher' in actor:
                frozen=fusion_asset(src,actor['fusion_teacher']);name=frozen.relative_to(src).as_posix()
                (stage/name).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(frozen,stage/name);shutil.copy2(str(frozen)+'.json',str(stage/name)+'.json')
                for extra in ('fusion_selection.json','fusion_refinement.json'):
                    if (src/extra).exists():shutil.copy2(src/extra,stage/extra)
            atomic_json(stage/'config.json',cfg)
            atomic_json(stage/'guard.json',dict(step=full['timesteps'],checks=0,regressions=0,decision='retain'))
            atomic_json(stage/'fork.json',dict(source_run=src.name,source_actor_sha256=actor['sha256'],
                source_full_sha256=full['sha256'],start_timesteps=full['timesteps'],objective_name=objective_name,
                seed=int(seed),critic_note='Optimizer/value weights retained; new objective needs value adaptation.'))
            session(stage,cfg,full['timesteps']);stage.rename(dst)
        finally:
            if stage.exists():shutil.rmtree(stage)
    print('EXPERIMENT_FORK_READY:',dst,flush=True)
    return dst


def evaluation_record(run,cfg,report,split,seed,pairs,seconds):
    """Keep tested weights and complete results; wdl.json stays a convenience copy."""
    from .triad_selector import selector_meta
    run=Path(run);info=provenance(cfg)
    latest=selector_meta(run/'latest.pt');initial=selector_meta(run/'initial.pt')
    if (report['candidate_sha256']!=latest['sha256'] or report['baseline_sha256']!=initial['sha256'] or
        report['candidate_timesteps']!=latest['timesteps']):raise ValueError('Report does not identify the saved tested checkpoints')
    out=bundle(run,run/'evaluations')
    prior=[]
    for p in (run/'evaluations').glob('*/evaluation.json'):
        d=json.loads(p.read_text())
        if d.get('split')==split and d.get('seed_start')==seed:prior.append(p.parent.name)
    save_source(run,info)
    info.update(split=split,seed_start=int(seed),pairs=int(pairs),seconds=float(seconds),
        candidate_sha256=report['candidate_sha256'],baseline_sha256=report['baseline_sha256'],
        previously_used_seed_bank=bool(prior),previous_evaluations=prior)
    atomic_json(out/'evaluation.json',info)
    atomic_json(out/'wdl.json',report)
    return out


def report(name='selector01'):
    """Small shareable report: selected metrics/metadata, no weights or raw logs."""
    run=run_path(name);out=run.parent.parent/'reports'/f'{name}_research_{stamp()}.zip';out.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for n in ('guard.json','wdl.json','fusion_selection.json','fusion_refinement.json','frozen_fusion.pt.json','six_origin.json'):
                if (run/n).exists():z.write(run/n,n)
            if (run/'status.json').exists():
                d=json.loads((run/'status.json').read_text());z.writestr('status.json',json.dumps({k:d[k] for k in ('state','timesteps','halt_reason','metrics','guard') if k in d},indent=2))
            cfg=json.loads((run/'config.json').read_text());z.writestr('objective.json',json.dumps(definition(cfg),indent=2))
            for p in (run/'evaluations').glob('*/evaluation.json'):
                d=json.loads(p.read_text());d.pop('files',None)
                z.writestr('evaluations/'+p.parent.name+'/evaluation.json',json.dumps(d,indent=2))
                z.write(p.parent/'wdl.json','evaluations/'+p.parent.name+'/wdl.json')
            pointer=run/'diagnostics/latest.json'
            if pointer.exists():
                target=(run/json.loads(pointer.read_text())['path']/'diagnostic.json').resolve()
                if not target.is_relative_to((run/'diagnostics').resolve()):raise ValueError('Diagnostic report path escapes its run')
                z.write(target,'latest_diagnostic.json')
            pointer=run/'six_diagnostics/latest.json'
            if pointer.exists():
                target=(run/json.loads(pointer.read_text())['path']/'diagnostic.json').resolve()
                if not target.is_relative_to((run/'six_diagnostics').resolve()):raise ValueError('Six-expert report path escapes its run')
                z.write(target,'latest_six_diagnostic.json')
            z.writestr('limits.txt',LIMITS)
    print('RESEARCH_REPORT_READY:',out,flush=True)
    return out
