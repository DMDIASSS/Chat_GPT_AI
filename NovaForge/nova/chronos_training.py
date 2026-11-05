"""Checkpoint-safe Chronos fine tuning. Teacher assets are immutable inputs."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import tempfile
import time

import numpy as np
import torch
from filelock import FileLock
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure
from stable_baselines3.common.vec_env import DummyVecEnv,SubprocVecEnv

from .core import ROOT,atomic_json,check_model,write_model_meta,sha256
from .models import save_ppo,_sync_serialized_file
from .teachers import verify_teacher
from .giga_teachers import GigaNetwork
from .chronos import CHRONOS_CONTRACT,ChronosEnv,ChronosPolicy,ChronosPPO
from .tracking import Tracker,WandBWriter,EpisodeWindow
from .training import load_config,prepare_config,archive_progress_csv,learn_segments


def resolve_chronos(path):
    path=Path(path).resolve()
    if path.is_dir():
        record=json.loads((path/'latest.json').read_text())
        selected=(path/record['path']).resolve()
        if not selected.is_relative_to(path):raise ValueError('Chronos checkpoint escapes its run')
        path=selected
    check_model(path,CHRONOS_CONTRACT)
    return path


def recover_chronos(run):
    """Resume from the newest complete generation after an interrupted save."""
    run=Path(run)
    for path in sorted((run/'checkpoints').glob('step_*.zip'),reverse=True):
        try:meta=check_model(path,CHRONOS_CONTRACT)
        except (OSError,ValueError,KeyError):continue
        atomic_json(run/'latest.json',dict(path=str(path.relative_to(run)),step=meta['timesteps'],contract=CHRONOS_CONTRACT))
        return path
    raise FileNotFoundError('No complete Chronos checkpoint is available')


def complete_generation(path):
    """Preserve incomplete bytes for diagnosis before writing a replacement."""
    path=Path(path)
    if not path.exists():return False
    try:check_model(path,CHRONOS_CONTRACT);return True
    except (OSError,ValueError,KeyError):
        stamp=str(time.time_ns())
        path.rename(path.with_name(path.name+'.incomplete-'+stamp))
        sidecar=Path(str(path)+'.json')
        if sidecar.exists():sidecar.rename(sidecar.with_name(sidecar.name+'.incomplete-'+stamp))
        return False


def export_chronos_actor(model,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    actor=copy.deepcopy(model.policy.actor).cpu().eval().requires_grad_(False)
    scripted=torch.jit.script(actor)
    with torch.inference_mode():
        example=torch.linspace(-1,1,450).reshape(2,225)
        torch.testing.assert_close(scripted(example),actor(example),rtol=0,atol=0)
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.lt');os.close(fd)
    try:
        torch.jit.save(scripted,temp);_sync_serialized_file(temp);os.replace(temp,path)
        write_model_meta(path,contract=CHRONOS_CONTRACT,timesteps=int(model.num_timesteps),role='chronos_actor')
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path


def load_network(path):
    path=resolve_chronos(path)
    if path.suffix=='.zip':
        model=ChronosPPO.load(path,device='cpu')
        actor=model.policy.actor.eval().requires_grad_(False)
        return actor
    if path.suffix not in {'.lt','.pt'}:raise ValueError('Expected a Chronos checkpoint or exported actor')
    actor=torch.jit.load(str(path),map_location='cpu').eval()
    for parameter in actor.parameters():parameter.requires_grad_(False)
    return actor


class ChronosRunner:
    def __init__(self,path):
        self.path=resolve_chronos(path);self.actor=load_network(self.path)
    def action(self,obs):
        with torch.inference_mode():
            logits=self.actor(torch.from_numpy(obs[:225])[None,:])[0].numpy()
        if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid Chronos actor output')
        return int(np.where(obs[225:]>0,logits,-np.inf).argmax())


def make_chronos_vector(cfg,run):
    factories=[]
    for _ in range(cfg['workers']):
        def factory():
            torch.set_num_threads(cfg['threads'])
            return ChronosEnv(cfg,league_manifest=Path(run)/'league.json')
        factories.append(factory)
    vec=DummyVecEnv(factories) if cfg['workers']==1 else SubprocVecEnv(factories,start_method='spawn')
    vec.seed(cfg['seed'])
    return vec


def new_chronos_model(cfg,env,initialize=True):
    p=dict(cfg['ppo']);p.pop('net_arch',None)
    settings=cfg['chronos']
    for key in ('actor_lr','critic_lr'):
        if not np.isfinite(settings[key]) or settings[key]<=0:raise ValueError('Chronos learning rates must be finite and positive')
    if not np.isfinite(settings['anchor_coef']) or settings['anchor_coef']<0:raise ValueError('Invalid Chronos anchor coefficient')
    if not isinstance(settings['critic_warmup_updates'],int) or settings['critic_warmup_updates']<0:raise ValueError('Invalid critic warmup count')
    if settings.get('checkpoints_keep',3)<1:raise ValueError('Keep at least one training checkpoint')
    model=ChronosPPO(ChronosPolicy,env,device=cfg['device'],seed=cfg['seed'],verbose=1,
        actor_lr=settings['actor_lr'],critic_lr=settings['critic_lr'],anchor_coef=settings['anchor_coef'],
        critic_warmup_updates=settings['critic_warmup_updates'],**p)
    if initialize:
        original=GigaNetwork(verify_teacher('chronos'),'chronos')
        model.policy.actor.load_state_dict(original.state_dict(),strict=True)
        model.policy.anchor.load_state_dict(original.state_dict(),strict=True)
    return model


class ChronosCallback(BaseCallback):
    def __init__(self,run,cfg,tracker,continuous):
        super().__init__();self.run=Path(run);self.cfg=cfg;self.tracker=tracker;self.continuous=continuous
        self.started=time.monotonic();self.start_step=None;self.last_saved=-1;self.window=EpisodeWindow()

    def persist(self,force=False):
        step=int(self.model.num_timesteps)
        if not force and self.last_saved>=0 and step-self.last_saved<self.cfg['league']['snapshot_every']:return
        full=self.run/'checkpoints'/f'step_{step:012d}.zip'
        actor=self.run/'snapshots'/f'step_{step:012d}.lt'
        if not complete_generation(full):save_ppo(self.model,full,contract=CHRONOS_CONTRACT,initialization='pretrained_chronos_anchored_ppo')
        check_model(full,CHRONOS_CONTRACT)
        if not complete_generation(actor):export_chronos_actor(self.model,actor)
        check_model(actor,CHRONOS_CONTRACT)
        atomic_json(self.run/'latest.json',dict(path=str(full.relative_to(self.run)),step=step,contract=CHRONOS_CONTRACT))
        manifest=self.run/'league.json'
        entries=json.loads(manifest.read_text())['snapshots'] if manifest.exists() else []
        if not any(e['step']==step for e in entries):entries.append(dict(path=str(actor.relative_to(self.run)),step=step))
        entries=entries[-self.cfg['league']['history_size']:]
        atomic_json(manifest,dict(contract=CHRONOS_CONTRACT,snapshots=entries))
        # Switch durable pointers before removing inactive generations. Initial is retained.
        keep={self.run/e['path'] for e in entries}|{self.run/'snapshots/step_000000000000.lt'}
        for file in (self.run/'snapshots').glob('step_*.lt'):
            if file not in keep:
                file.unlink();Path(str(file)+'.json').unlink(missing_ok=True)
        saved=sorted((self.run/'checkpoints').glob('step_*.zip'),reverse=True)
        for file in saved[self.cfg['chronos'].get('checkpoints_keep',3):]:
            if file.name!='step_000000000000.zip':
                file.unlink();Path(str(file)+'.json').unlink(missing_ok=True)
        self.last_saved=step
        self.status('saved')

    def status(self,state):
        step=int(self.model.num_timesteps)
        if self.start_step is None:self.start_step=step
        metrics=dict(self.window.metrics(),**{'trainer/learner_decisions_per_second':(step-self.start_step)/max(time.monotonic()-self.started,.01),
                    'trainer/chronos_updates':self.model.chronos_updates})
        self.tracker.log(metrics,step);self.tracker.save_status()
        atomic_json(self.run/'status.json',dict(trainer='chronos_ppo_v1',state=state,timesteps=step,
            decision_ticks=8,session_seconds=time.monotonic()-self.started,metrics=metrics,
            chronos_updates=self.model.chronos_updates,critic_warmup_updates=self.model.critic_warmup_updates,
            continuous=self.continuous,wandb=self.tracker.status()))

    def _on_rollout_start(self):self.persist()
    def _on_step(self):
        for info in self.locals.get('infos',[]):
            if 'outcome' in info:
                self.window.add(info)
                row={k:info[k] for k in ('scenario','opponent','side','outcome','timeout','practice_success',
                    'touches','high_touch','wall_touch','dribble_seconds','seconds','reward_parts','episode')}
                with (self.run/'episodes.jsonl').open('a',encoding='utf8') as f:
                    f.write(json.dumps(dict(row,timesteps=int(self.model.num_timesteps)))+'\n')
        if self.n_calls%250==0:self.status('training')
        return not (self.run/'STOP').exists()
    def _on_training_end(self):self.persist(force=True)


def train_chronos(args):
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Run name must be one folder name')
    run.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run/'train.lock'),timeout=0):
        if args.resume:
            cfg=load_config(run/'config.json')
            if cfg.get('trainer')!='chronos_ppo_v1':raise ValueError('This is not a Chronos PPO run')
            source=recover_chronos(run)
            provenance=json.loads((run/'provenance.json').read_text())
            if provenance['teacher_lock_sha256']!=sha256(ROOT/'teachers.lock.json'):
                raise ValueError('Teacher lock changed since this Chronos run began')
        else:
            if (run/'config.json').exists():raise FileExistsError('Run exists; use --resume')
            cfg=prepare_config(load_config(args.config))
            cfg['trainer']='chronos_ppo_v1';source=None
        if args.device:cfg['device']=args.device
        for name in ('chronos','nexto','ripple','galactus'):verify_teacher(name)
        torch.set_num_threads(cfg['threads'])
        vec=None;callback=None;tracker=None;result='error';model=None
        try:
            tracker=Tracker(run,cfg,mode=args.wandb,continuous=args.forever)
            vec=make_chronos_vector(cfg,run)
            model=ChronosPPO.load(source,env=vec,device=cfg['device']) if source else new_chronos_model(cfg,vec)
            if not source:
                atomic_json(run/'config.json',cfg)
                atomic_json(run/'provenance.json',dict(contract=CHRONOS_CONTRACT,teacher_lock_sha256=sha256(ROOT/'teachers.lock.json'),
                    original_chronos={file:sha256(verify_teacher('chronos')/file) for file in ['POLICY.lt','SHARED_HEAD.lt']}))
            archive_progress_csv(run)
            model.set_logger(configure(str(run/'logs'),['stdout','csv']))
            if tracker.run is not None:model.logger.output_formats.append(WandBWriter(tracker))
            (run/'STOP').unlink(missing_ok=True)
            callback=ChronosCallback(run,cfg,tracker,args.forever);callback.init_callback(model)
            callback.persist(force=True)
            print('Chronos weights loaded directly. Eight-tick masked PPO; frozen opponents and snapshot self-play.',flush=True)
            try:result=learn_segments(model,callback,args.steps,args.forever,run/'STOP')
            except KeyboardInterrupt:result='stopped'
        finally:
            try:
                if model is not None and callback is not None:
                    callback.persist(force=True);callback.status(result)
                    verify_teacher('chronos')
            finally:
                if vec is not None:vec.close()
                if tracker is not None:
                    tracker.finish(result)
                    if model is not None and callback is not None:callback.status(result)
    print(f'CHRONOS_{result.upper()}: {run}',flush=True)
