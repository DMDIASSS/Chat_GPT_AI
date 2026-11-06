"""Paired, blind-actor W/D/L. Train/dev/confirmation/test seed ranges differ."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from .core import atomic_json, check_model
from .forge_env import ForgeEnv
from .forge_models import CORE, contract,check_actor

SEEDS={'development':410000000,'confirmation':710000000,'test':1410000000}


class Stopped(Exception):pass


def summary(rows):
    n=len(rows)
    return dict(matches=n,wins=sum(r['outcome']==1 for r in rows),draws=sum(r['outcome']==0 for r in rows),
        losses=sum(r['outcome']==-1 for r in rows),goals_for=sum(r['goals_for'] for r in rows),
        goals_against=sum(r['goals_against'] for r in rows),
        score_rate=float(np.mean([(r['outcome']+1)/2 for r in rows])) if n else None)


def paired(a,b):
    key=lambda r:(r['opponent'],r['seed'],r['side'])
    by={key(r):r for r in b}
    if len(by)!=len(b) or len(a)!=len(b) or len({key(r) for r in a})!=len(a):raise ValueError('Unpaired results')
    blocks={};per={}
    for r in a:
        old=by[key(r)]
        # Pair both colors into a block; outcome is win=1, draw=.5, loss=0.
        d=(r['outcome']-old['outcome'])/2
        blocks.setdefault((r['opponent'],r['seed']),[]).append(d)
        per.setdefault(r['opponent'],[]).append(d)
    if not blocks or any(len(v)!=2 for v in blocks.values()):raise ValueError('Each seed requires both colors')
    # Stratified uncertainty: opponents are a fixed panel, not IID draws from
    # an imagined population. Require at least four seeds in every stratum.
    strata={}
    for (opponent,_),values in blocks.items():strata.setdefault(opponent,[]).append(float(np.mean(values)))
    means=[np.mean(v) for v in strata.values()]
    se=(sum(np.var(v,ddof=1)/len(v) for v in strata.values())**.5/len(strata)
        if min(map(len,strata.values()))>=4 else None)
    delta=float(np.mean(means));margin=max(1e-6,2.576*se) if se is not None else None
    return dict(blocks=len(blocks),delta=delta,standard_error=se,
        lower=delta-margin if margin is not None else None,upper=delta+margin if margin is not None else None,
        by_opponent={k:float(np.mean(v)) for k,v in per.items()},
        caution='Approximate 99% paired interval; repeated adaptive checks are not a lifetime guarantee.')


def judgement(stats,settings):
    if stats['lower'] is None:return 'uncertain'
    if (stats['lower']>0 and stats['delta']>=settings['minimum_delta']
            and min(stats['by_opponent'].values())>=-settings['per_opponent_tolerance']):return 'improved'
    if stats['upper'] < -settings['regression_delta']:return 'regressed'
    return 'uncertain'


def action(actor,obs,family):
    size=CORE[family]+3
    with torch.inference_mode():logits=actor(torch.from_numpy(obs[:size])[None,:])[0].numpy()
    if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Nonfinite evaluation actor')
    return int(np.where(obs[size:size+90]>0,logits,-np.inf).argmax())


def suite(cfg,family,candidate,baseline,panel,split,cycle,stop_path,*,pairs=None,seconds=None,output=None):
    settings=cfg['evaluation'];pairs=settings['pairs'] if pairs is None else pairs;seconds=settings['seconds'] if seconds is None else seconds
    if pairs<1 or seconds<=0:raise ValueError('Invalid evaluation budget')
    rows=[[],[]];paths=[Path(candidate),Path(baseline)]
    actors=[]
    for p in paths:
        meta=check_actor(p,family)
        if meta['contract']['hitbox']!=cfg.get('hitboxes',{}).get(family,'octane'):raise ValueError('Evaluation hitbox differs from actor contract')
        actors.append(torch.jit.load(str(p),map_location='cpu').eval())
    total=len(panel)*pairs*4;done=0;started=time.monotonic()
    print(f'FORGE_EVAL: {split}, {total} games x {seconds:g}s; actors have no private inputs.',flush=True)
    for cell,entry in enumerate(panel):
        for pair in range(pairs):
            seed=SEEDS[split]+cycle*1000000+cell*10000+pair
            for side in (0,1):
                env=ForgeEnv(cfg,family,[entry],profile='match',side=side,scenario='kickoff',seconds=seconds)
                try:
                    first=None
                    for index,actor in enumerate(actors):
                        obs,_=env.reset(seed=seed)
                        digest=hashlib.sha256(obs.tobytes()).hexdigest()
                        if first is None:first=digest
                        elif digest!=first:raise RuntimeError('Paired starting observations differ')
                        last_notice=time.monotonic()
                        while True:
                            if Path(stop_path).exists():raise Stopped()
                            obs,_,terminal,_,info=env.step(action(actor,obs,family))
                            if terminal:break
                            if time.monotonic()-last_notice>=5:
                                print(f'EVAL game {done+1}/{total}: {env.decisions/15:.0f}/{seconds:g}s, {env.goals_for}:{env.goals_against}',flush=True)
                                last_notice=time.monotonic()
                        row={k:info[k] for k in ('opponent','side','outcome','goals_for','goals_against','touches','seconds')}
                        row.update(seed=seed,initial_observation_sha256=digest)
                        rows[index].append(row);done+=1
                        print(f'EVAL {done}/{total} {family}/{"candidate" if index==0 else "reference"} vs {entry["name"]}: {info["goals_for"]}:{info["goals_against"]}',flush=True)
                finally:env.close()
        print('EVAL_OPPONENT',entry['name'],summary([r for r in rows[0] if r['opponent']==entry['name']]),flush=True)
    report=dict(kind='forgeleague-blind-timed-1v1-v1',family=family,split=split,cycle=cycle,
        candidate_sha256=check_actor(paths[0],family)['sha256'],
        baseline_sha256=check_actor(paths[1],family)['sha256'],
        summary=summary(rows[0]),baseline_summary=summary(rows[1]),statistics=paired(*rows),
        trials=rows[0],baseline_trials=rows[1],wall_seconds=time.monotonic()-started,
        note='Simulator matches; no goal pauses or overtime. Equal scores are draws. No live RLBot strength claim.')
    if output:atomic_json(output,report)
    return report
