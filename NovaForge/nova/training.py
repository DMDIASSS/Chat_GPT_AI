from __future__ import annotations

import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from filelock import FileLock
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from .core import ROOT, CONTRACT, atomic_json, check_model, sha256
from .environment import ArenaEnv
from .models import export_actor, load_ppo, save_ppo
from .teachers import verify_teacher, BOT_NAMES,FROZEN_BOTS
from .tracking import Tracker, WandBWriter, EpisodeWindow


def recover_checkpoint(run_dir):
    """Use the newest complete generation, even if a crash preceded pointer update."""
    run_dir=Path(run_dir)
    for path in sorted((run_dir/'checkpoints').glob('step_*.zip'),reverse=True):
        try:
            meta=check_model(path)
        except (ValueError,OSError,json.JSONDecodeError):
            continue
        atomic_json(run_dir/'latest.json',dict(path=str(path.relative_to(run_dir)),
                                               step=meta['timesteps'],contract=CONTRACT))
        return path
    raise FileNotFoundError('No complete checkpoint in this run; fix the startup error and choose a new run name')


def load_config(path=None):
    cfg=json.loads(Path(path or ROOT/'configs/laptop.json').read_text(encoding='utf8'))
    validate_config(cfg)
    return cfg


def validate_config(cfg):
    if cfg['workers']<1 or cfg['workers']>8 or cfg['threads']<1:
        raise ValueError('Choose 1..8 workers and at least one torch thread')
    p=cfg['ppo']
    if p['n_steps']<2 or p['batch_size']<2 or cfg['workers']*p['n_steps']%p['batch_size']:
        raise ValueError('PPO batch_size must divide workers*n_steps')
    if cfg['env']['episode_seconds']<=0 or cfg['env']['no_touch_seconds']<=0:
        raise ValueError('Episode and no-touch limits must be positive')
    for key in ['league','curriculum']:
        w=cfg[key]['weights']
        if not w or any(not np.isfinite(x) or x<0 for x in w.values()) or sum(w.values())<=0:
            raise ValueError(f'Invalid {key} weights')
    if set(cfg['league']['weights'])-(set(BOT_NAMES)|{'latest','history'}):
        raise ValueError('No headless adapter for one of the league opponents')
    if set(cfg['curriculum']['weights'])-{'kickoff','shot','defense','dribble','aerial','recovery','wall','replay'}:
        raise ValueError('Unsupported practice scenario')
    if cfg['league']['snapshot_every']<1 or cfg['league']['history_size']<1:
        raise ValueError('Invalid snapshot settings')
    if cfg['rewards'] not in ('shaped','sparse'):
        raise ValueError('Rewards must be shaped or sparse')


def prepare_config(cfg,teachers=None,replay_bank=None):
    cfg=json.loads(json.dumps(cfg))
    if teachers:
        names=[s.strip() for s in teachers.split(',') if s.strip()]
        if len(names)!=len(set(names)) or set(names)-set(FROZEN_BOTS):
            raise ValueError('Supported teachers: nexto,ripple,chronos,galactus')
        cfg['league']['weights']={'scripted':.2,'latest':.3,'history':.2,
                                  **{n:.3/len(names) for n in names}}
    if replay_bank:
        cfg['env']['replay_bank']=str(Path(replay_bank).resolve())
        cfg['curriculum']['weights']['replay']=.25
    if cfg['env'].get('replay_bank'):
        bank=Path(cfg['env']['replay_bank']).resolve()
        digest=sha256(bank)
        expected=cfg['env'].get('replay_bank_sha256')
        if expected and digest!=expected: raise ValueError('Replay reset bank changed since this run was configured')
        cfg['env'].update(replay_bank=str(bank),replay_bank_sha256=digest)
    for name,weight in cfg['league']['weights'].items():
        if name in FROZEN_BOTS and weight>0: verify_teacher(name)
    validate_config(cfg)
    return cfg


def make_vector(cfg,run_dir):
    factories=[]
    for worker in range(cfg['workers']):
        def factory(index=worker):
            torch.set_num_threads(cfg['threads'])
            env=ArenaEnv(cfg,league_manifest=Path(run_dir)/'league.json')
            return env
        factories.append(factory)
    vec=DummyVecEnv(factories) if cfg['workers']==1 else SubprocVecEnv(factories,start_method='spawn')
    vec.seed(cfg['seed'])
    return vec


def new_model(cfg,env):
    params=dict(cfg['ppo'])
    layers=params.pop('net_arch')
    return PPO('MlpPolicy',env,policy_kwargs=dict(net_arch=dict(pi=layers,vf=layers)),
               device=cfg['device'],seed=cfg['seed'],verbose=1,**params)


def resolve_model(path,copy_checkpoint='published'):
    if copy_checkpoint not in {'published','validation','resume'}:raise ValueError('Unknown copy checkpoint selection')
    path=Path(path).resolve()
    record=None
    if path.is_dir():
        if copy_checkpoint=='published':
            record=json.loads((path/'latest.json').read_text())
        else:
            state=json.loads((path/'copy_state.json').read_text())
            record=state['best' if copy_checkpoint=='validation' else 'resume']
        selected=(path/record['path']).resolve()
        if not selected.is_relative_to(path):raise ValueError('Checkpoint path escapes its run')
        path=selected
    elif copy_checkpoint!='published':
        raise ValueError('Copy checkpoint selection requires a copy run folder')
    meta=check_model(path)
    if record and record.get('sha256') and record['sha256']!=meta['sha256']:
        raise ValueError('Selected checkpoint hash does not match its run record')
    return path


class LeagueCallback(BaseCallback):
    def __init__(self,run_dir,cfg,tracker=None,continuous=False):
        super().__init__()
        self.run_dir=Path(run_dir)
        self.cfg=cfg
        self.last_saved=-cfg['league']['snapshot_every']
        self.started=time.monotonic()
        self.start_step=0
        self.episodes=0
        self.wins=0
        self.losses=0
        self.timeouts=0
        self.tracker=tracker
        self.continuous=continuous
        self.window=EpisodeWindow()
        self.session_started=False

    def _on_training_start(self):
        if not self.session_started:
            self.start_step=self.num_timesteps
            self.started=time.monotonic()
            self.session_started=True

    def persist(self,force=False):
        step=int(self.model.num_timesteps)
        if not force and step-self.last_saved<self.cfg['league']['snapshot_every']:
            return
        full=self.run_dir/'checkpoints'/f'step_{step:012d}.zip'
        complete=False
        if full.exists():
            try:
                check_model(full)
                complete=True
            except (ValueError,OSError,json.JSONDecodeError):
                # An incomplete unpublished generation can remain after power loss.
                # Preserve it for diagnosis before writing a complete replacement.
                stamp=time.time_ns()
                full.rename(full.with_name(full.name+f'.incomplete-{stamp}'))
                sidecar=Path(str(full)+'.json')
                if sidecar.exists(): sidecar.rename(Path(str(sidecar)+f'.incomplete-{stamp}'))
        if not complete: save_ppo(self.model,full)
        atomic_json(self.run_dir/'latest.json',dict(path=str(full.relative_to(self.run_dir)),
                                                  step=step,contract=CONTRACT))
        actor=self.run_dir/'snapshots'/f'step_{step:012d}.pt'
        if actor.exists():
            try:
                check_model(actor)
            except (ValueError,OSError,json.JSONDecodeError):
                stamp=time.time_ns()
                actor.rename(actor.with_name(actor.name+f'.incomplete-{stamp}'))
                sidecar=Path(str(actor)+'.json')
                if sidecar.exists(): sidecar.rename(Path(str(sidecar)+f'.incomplete-{stamp}'))
        if not actor.exists(): export_actor(self.model,actor)
        manifest=self.run_dir/'league.json'
        entries=json.loads(manifest.read_text())['snapshots'] if manifest.exists() else []
        if not any(x['step']==step for x in entries):
            entries.append(dict(path=str(actor.relative_to(self.run_dir)),step=step))
        atomic_json(manifest,dict(snapshots=entries[-self.cfg['league']['history_size']:],contract=CONTRACT))
        self.last_saved=step
        self.status('saved')

    def status(self,state):
        fps=(self.model.num_timesteps-self.start_step)/max(time.monotonic()-self.started,.01)
        if self.tracker:
            self.tracker.log(dict(self.window.metrics(),**{'trainer/fps':fps,
                'trainer/session_episodes':self.episodes,'trainer/continuous':int(self.continuous)}),
                self.model.num_timesteps)
            self.tracker.save_status()
        atomic_json(self.run_dir/'status.json',dict(state=state,timesteps=int(self.model.num_timesteps),
            fps_since_start=fps,continuous=self.continuous,updated_unix_time=time.time(),
            episodes_this_session=self.episodes,wins=self.wins,losses=self.losses,timeouts=self.timeouts,
            latest='latest.json',session_seconds=time.monotonic()-self.started,
            wandb=self.tracker.status() if self.tracker else {'mode':'off'}))

    def _on_rollout_start(self):
        # SB3 has completed the preceding PPO update at this point.
        self.persist()

    def _on_step(self):
        for info in self.locals.get('infos',[]):
            if 'outcome' in info:
                self.episodes+=1
                self.wins+=info['outcome']==1
                self.losses+=info['outcome']==-1
                self.timeouts+=info['timeout']
                fields=('outcome','timeout','practice_success','touches','high_touch','wall_touch',
                        'dribble_seconds','seconds','reward_parts','episode','scenario','opponent','side')
                record={k:info[k] for k in fields}
                self.window.add(record)
                record.update(timesteps=self.num_timesteps,unix_time=time.time())
                with (self.run_dir/'episodes.jsonl').open('a',encoding='utf8') as f:
                    f.write(json.dumps(record,allow_nan=False)+'\n')
        if self.n_calls%500==0: self.status('training')
        return not (self.run_dir/'STOP').exists()

    def _on_training_end(self):
        self.persist(force=True)
        self.model.logger.dump(step=self.model.num_timesteps)
        self.status('stopped' if (self.run_dir/'STOP').exists() else
                    'training' if self.continuous else 'finished')


def learn_segments(model,callback,steps,continuous,stop_path):
    """Keep one model/vector environment alive across bounded PPO segments."""
    if steps<=0: raise ValueError('Segment size must be positive')
    while not Path(stop_path).exists():
        model.learn(total_timesteps=steps,callback=callback,reset_num_timesteps=False,
                    log_interval=1,progress_bar=False)
        if Path(stop_path).exists(): return 'stopped'
        if not continuous: return 'finished'
    return 'stopped'


def archive_progress_csv(run_dir):
    path=Path(run_dir)/'logs'/'progress.csv'
    if path.exists():
        history=path.parent/'history'
        history.mkdir(parents=True,exist_ok=True)
        path.replace(history/f'progress_{time.time_ns()}.csv')


def train(args):
    run_dir=(ROOT/'runs'/args.run).resolve()
    if run_dir.parent != (ROOT/'runs').resolve():
        raise ValueError('Run name must be a single folder name')
    run_dir.mkdir(parents=True,exist_ok=True)
    with FileLock(str(run_dir/'train.lock'),timeout=0):
        if args.resume:
            if any([args.teachers,args.replay_bank,args.init,args.config,args.workers,args.device]):
                raise ValueError('Resume uses the saved run config; omit config/teachers/init/workers/device overrides')
            cfg=load_config(run_dir/'config.json')
            prepare_config(cfg)
            source=recover_checkpoint(run_dir)
        else:
            if (run_dir/'config.json').exists():
                raise FileExistsError('Run already exists. Use --resume or choose a fresh --run name')
            cfg=load_config(args.config)
            if args.workers: cfg['workers']=args.workers
            if args.device: cfg['device']=args.device
            cfg=prepare_config(cfg,args.teachers,args.replay_bank)
            source=resolve_model(args.init) if args.init else None
        continuous=getattr(args,'forever',False)
        tracker=Tracker(run_dir,cfg,mode=getattr(args,'wandb',None),
                        project=getattr(args,'wandb_project',None),
                        entity=getattr(args,'wandb_entity',None),continuous=continuous)
        vec=None
        callback=None
        result='error'
        try:
            if not args.resume:
                atomic_json(run_dir/'config.json',cfg)
                import importlib.metadata as metadata
                atomic_json(run_dir/'provenance.json',dict(contract=CONTRACT,platform=platform.platform(),
                    packages={p:metadata.version(p) for p in ['torch','numpy','stable-baselines3',
                            'rlgym-rocket-league','rlgym-tools','RocketSim','onnxruntime']},
                    initialization=str(source) if source else 'random'))
            (run_dir/'STOP').unlink(missing_ok=True)
            torch.set_num_threads(cfg['threads'])
            vec=make_vector(cfg,run_dir)
            callback=LeagueCallback(run_dir,cfg,tracker=tracker,continuous=continuous)
            model=load_ppo(source,vec,cfg['device']) if source else new_model(cfg,vec)
            if source and not args.resume:
                # Keep BC policy weights; initialize PPO with this run's settings.
                # Model creation supplies the chosen optimizer/hyperparameters.
                imported=new_model(cfg,vec)
                imported.policy.load_state_dict(model.policy.state_dict())
                model=imported
            archive_progress_csv(run_dir)
            model.set_logger(configure(str(run_dir/'logs'),['stdout','csv']))
            if tracker.run is not None: model.logger.output_formats.append(WandBWriter(tracker))
            print('Training until pause/Ctrl+C.' if continuous else f'Training for {args.steps} additional decisions.',flush=True)
            try:
                result=learn_segments(model,callback,args.steps,continuous,run_dir/'STOP')
            except KeyboardInterrupt:
                callback.persist(force=True)
                callback.status('interrupted; saved')
                result='interrupted; saved'
                print('Interrupted. Last policy and optimizer saved; resume the same run.')
        finally:
            try:
                if vec is not None: vec.close()
            finally:
                tracker.finish(result)
                if callback is not None and hasattr(callback,'model'): callback.status(result)
    print(f'Checkpoint pointer: {run_dir/"latest.json"}')
