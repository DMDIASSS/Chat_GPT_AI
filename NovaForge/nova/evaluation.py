from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from .core import ACTIONS, atomic_json, sha256
from .environment import ArenaEnv
from .models import FrozenActor, export_actor, load_ppo
from .training import load_config, resolve_model


class Student:
    def __init__(self,path):
        self.path=resolve_model(path)
        self.actor=FrozenActor(self.path) if self.path.suffix=='.pt' else None
        self.model=None if self.actor else load_ppo(self.path)

    def action(self,obs):
        if self.actor: return self.actor.action(obs)
        return int(self.model.predict(obs,deterministic=True)[0])


def summarize(rows):
    n=len(rows)
    wins=sum(r['outcome']==1 for r in rows)
    losses=sum(r['outcome']==-1 for r in rows)
    timeouts=sum(r['timeout'] for r in rows)
    return dict(trials=n,first_goal_wins=wins,first_goal_losses=losses,timeouts=timeouts,
        first_goal_score_fraction=wins/max(n,1),resolved_fraction=(wins+losses)/max(n,1),
        practice_success_fraction=sum(r['practice_success'] for r in rows)/max(n,1),
        touches_per_trial=sum(r['touches'] for r in rows)/max(n,1))


def evaluate(args):
    torch.set_num_threads(1)
    student=Student(args.model)
    baseline=Student(args.baseline) if args.baseline else None
    cfg=load_config(args.config)
    cfg['env']['episode_seconds']=args.seconds
    # Evaluation ends on a goal or the advertised horizon, never a training idle timeout.
    cfg['env']['no_touch_seconds']=args.seconds+1
    cfg['curriculum']['adaptive']=False
    opponents=[x.strip() for x in args.opponents.split(',')]
    scenarios=[x.strip() for x in args.scenarios.split(',')]
    if set(opponents)-{'scripted','nexto','ripple'}: raise ValueError('Unsupported evaluation opponent')
    if set(scenarios)-set(cfg['curriculum']['weights']): raise ValueError('Unknown evaluation scenario')
    if Path(args.out).exists(): raise FileExistsError('Choose a fresh report filename')
    rows=[]
    baseline_rows=[]
    for opponent in opponents:
        for scenario in scenarios:
            for pair in range(args.pairs):
                seed=args.seed+pair
                for side in (0,1):
                    env=ArenaEnv(cfg,opponent=opponent,scenario=scenario,side=side)
                    try:
                        for label,policy,destination in [('candidate',student,rows),('baseline',baseline,baseline_rows)]:
                            if policy is None: continue
                            obs,_=env.reset(seed=seed)
                            while True:
                                obs,_,terminal,truncated,info=env.step(policy.action(obs))
                                if terminal or truncated: break
                            destination.append(dict(info,seed=seed,policy=label))
                    finally:
                        env.close()
                print(f'{opponent}/{scenario}: pair {pair+1}/{args.pairs}',flush=True)
    breakdown={}
    for opponent in opponents:
        breakdown[opponent]={s:summarize([r for r in rows if r['opponent']==opponent and r['scenario']==s])
                             for s in scenarios}
    report=dict(kind='first_goal_trials',candidate=str(student.path),candidate_sha256=sha256(student.path),
        seconds_per_trial=args.seconds,seed_start=args.seed,paired_team_sides=True,
        summary=summarize(rows),breakdown=breakdown,trials=rows,
        note='Simulator screening only. Timeouts are censored trials, not draws or wins. No automatic promotion.')
    if baseline:
        delta=np.array([a['outcome']-b['outcome'] for a,b in zip(rows,baseline_rows)])
        report.update(baseline=str(baseline.path),baseline_sha256=sha256(baseline.path),
            baseline_summary=summarize(baseline_rows),baseline_trials=baseline_rows,
            paired_mean_outcome_delta=float(delta.mean()),
            paired_delta_standard_error=float(delta.std(ddof=1)/np.sqrt(len(delta))) if len(delta)>1 else None)
    atomic_json(args.out,report)
    print(json.dumps(report['summary'],indent=2))
    print(f'Report: {args.out}')


def export_rlbot(args):
    from .core import ROOT
    model_path=resolve_model(args.model)
    model=load_ppo(model_path)
    out=ROOT/'rlbot'/'policy.pt'
    export_actor(model,out,source_sha256=sha256(model_path))
    print(f'RLBot v5 config ready: {ROOT/"rlbot/novaforge.bot.toml"}')
    print('Add this config to the RLBot v5 GUI and select a 1v1 match.')


def watch(args):
    from rlgym.rocket_league.rlviser import RLViserRenderer
    torch.set_num_threads(1)
    student=Student(args.model)
    cfg=load_config(args.config)
    cfg['env']['episode_seconds']=args.seconds
    cfg['env']['no_touch_seconds']=args.seconds+1
    env=ArenaEnv(cfg,opponent=args.opponent,scenario=args.scenario)
    renderer=RLViserRenderer(tick_rate=30)
    print('Start the standalone RLViser application to view the UDP stream. Ctrl+C stops the viewer.')
    try:
        obs,_=env.reset(seed=args.seed)
        while True:
            started=time.monotonic()
            obs,_,terminal,truncated,info=env.step(student.action(obs))
            renderer.render(env.state,{})
            if terminal or truncated:
                print(json.dumps({k:info[k] for k in ['outcome','timeout','scenario','touches']}),flush=True)
                obs,_=env.reset()
            time.sleep(max(0,1/30-(time.monotonic()-started)))
    except KeyboardInterrupt:
        pass
    finally:
        env.close()
