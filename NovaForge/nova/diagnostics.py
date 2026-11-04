from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import time
from pathlib import Path

import numpy as np
import torch

from .core import ROOT, CONTRACT, ACTIONS, atomic_json, check_model
from .environment import ArenaEnv
from .models import FrozenActor, load_ppo
from .training import load_config, resolve_model, train, prepare_config


def doctor(args):
    torch.set_num_threads(1)
    cfg=load_config(args.config)
    names=['scripted']+([n.strip() for n in args.teachers.split(',')] if args.teachers else [])
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay, _default_executable
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    if not Path(_default_executable).is_file(): raise FileNotFoundError('Bundled replay parser executable missing')
    report=dict(contract=CONTRACT,python=__import__('sys').version,replay_imports=True,
        cuda_available=torch.cuda.is_available(),cuda_device=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        packages={p:metadata.version(p) for p in ['torch','numpy','rlgym','rlgym-rocket-league',
                    'rlgym-tools','RocketSim','stable-baselines3','rlbot','onnxruntime']},checks=[])
    for name in names:
        started=time.monotonic()
        for side in (0,1):
            env=ArenaEnv(cfg,opponent=name,scenario='kickoff',side=side)
            try:
                obs,_=env.reset(seed=3301)
                for _ in range(60):
                    obs,reward,terminal,truncated,_=env.step(10)
                    assert np.isfinite(obs).all() and np.isfinite(reward)
                    if terminal or truncated: obs,_=env.reset()
            finally:
                env.close()
        record=dict(opponent=name,physics_decisions=120,seconds=time.monotonic()-started,passed=True)
        report['checks'].append(record)
        print(json.dumps(record),flush=True)
    atomic_json(ROOT/'reports'/'doctor.json',report)
    print('DOCTOR_PASS: actual simulator steps succeeded. See reports/doctor.json')


def smoke(args):
    cfg=prepare_config(load_config(getattr(args,'config',None)),getattr(args,'teachers',None))
    cfg['workers']=args.workers
    cfg['ppo'].update(n_steps=64,batch_size=64,n_epochs=2)
    cfg['env'].update(episode_seconds=2,no_touch_seconds=1)
    cfg['league']['snapshot_every']=128
    config_path=ROOT/'work'/f'{args.run}-config.json'
    atomic_json(config_path,cfg)
    base=dict(run=args.run,config=str(config_path),teachers=None,replay_bank=None,init=None,
              workers=None,device=None,resume=False,steps=512)
    train(argparse.Namespace(**base))
    before=resolve_model(ROOT/'runs'/args.run)
    old=check_model(before)['timesteps']
    base.update(config=None,resume=True,steps=128)
    train(argparse.Namespace(**base))
    current=resolve_model(ROOT/'runs'/args.run)
    new=check_model(current)['timesteps']
    if new<=old: raise AssertionError('Resume did not advance model timesteps')
    model=load_ppo(current)
    league=json.loads((ROOT/'runs'/args.run/'league.json').read_text())
    actor=FrozenActor(ROOT/'runs'/args.run/league['snapshots'][-1]['path'])
    env=ArenaEnv(cfg,opponent='snapshot',snapshot=actor_path(ROOT/'runs'/args.run),scenario='shot')
    try:
        obs,_=env.reset(seed=44321)
        for _ in range(20):
            assert int(model.predict(obs,deterministic=True)[0])==actor.action(obs)
            obs,_,terminal,truncated,_=env.step(actor.action(obs))
            if terminal or truncated: obs,_=env.reset()
    finally:
        env.close()
    atomic_json(ROOT/'reports'/f'{args.run}.json',dict(result='SMOKE_PASS',
        actual_ppo_timesteps=new,resumed_from=old,workers=args.workers,
        checkpoint=str(current),snapshot_parity=True,frozen_opponent_steps=20))
    print(f'SMOKE_PASS: PPO, checkpoint, resume and frozen actor parity passed ({new} decisions).')


def actor_path(run_dir):
    manifest=json.loads((Path(run_dir)/'league.json').read_text())
    return Path(run_dir)/manifest['snapshots'][-1]['path']
