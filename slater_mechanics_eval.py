"""Matched full-match model selection and held-out mechanics/retention checks."""
from __future__ import annotations

from pathlib import Path
from importlib.metadata import version

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
from slater_mechanics_env import MechanicsEnv
from slater_mechanics_core import mastery_verdict
from slater_v041_core import sha256,atomic_json,read_json,NEXTO_SHA
from slater_v041_worker import model_from_checkpoint


def load_actor(root,path,*,trainable=False):
    path=Path(path).resolve();vendor=root/'vendor/nexto/nexto-model.pt'
    if sha256(vendor)!=NEXTO_SHA:raise RuntimeError('Original Nexto changed')
    actor=model_from_checkpoint(path,vendor)
    if trainable:
        # A fresh independent TorchScript instance owns the trainable parameters.
        actor=torch.jit.load(str(vendor),map_location='cpu').eval()
        frozen=model_from_checkpoint(path,vendor)
        actor.load_state_dict(frozen.state_dict(),strict=True)
        for p in actor.parameters():p.requires_grad_(True)
    return actor


def greedy(actor,obs):
    with torch.no_grad():return int(base.logits_of(actor,base.to_tensors(obs)).argmax(-1).item())


def full_match(actor,rivals,*,rival,side,seed,seconds):
    env=MechanicsEnv(rivals,retention=True,max_seconds=seconds,fixed_side=side,fixed_rival=rival)
    target=round(seconds*120);ticks=0;goals_for=goals_against=0;kickoffs=0;scripts=0
    try:
        obs=env.reset(seed);kickoffs+=1
        while ticks<target:
            # Shorten the last episode instead of overshooting the match clock.
            env.max_seconds=(env.tick_count+target-ticks)/120
            before=env.tick_count;obs,_,done,info=env.step(greedy(actor,obs))
            ticks+=env.tick_count-before
            if done:
                goals_for+=int(info['outcome']==1);goals_against+=int(info['outcome']==-1)
                scripts+=info['script_physics_ticks']
                if ticks<target:obs=env.reset(seed+7919*kickoffs);kickoffs+=1
        if not done:scripts+=env.clock.script_physics_ticks
    finally:env.close()
    return {'rival':rival,'side':side,'seed':seed,'seconds':ticks/120,
            'goals_for':goals_for,'goals_against':goals_against,'goal_diff':goals_for-goals_against,
            'won':goals_for>goals_against,'lost':goals_for<goals_against,
            'draw':goals_for==goals_against,'kickoffs':kickoffs,'script_physics_ticks':scripts}


def interval(values,seed=119):
    values=np.asarray(values,dtype=float)
    if len(values)<2:return {'mean':float(values.mean()),'lower':None,'upper':None,'seeds':len(values)}
    rng=np.random.default_rng(seed)
    means=values[rng.integers(0,len(values),(4000,len(values)))].mean(1)
    return {'mean':float(values.mean()),'lower':float(np.quantile(means,.025)),
            'upper':float(np.quantile(means,.975)),'seeds':len(values)}


def compare_models(root,candidates,rival_paths,*,seeds,seconds,out,seed_base=510_000_000):
    """Resume raw match records, require fixed model hashes and protocol."""
    out=Path(out);partial=out.with_suffix('.partial.json')
    from round_robin_evaluator import weight_digest
    actors={n:load_actor(root,p) for n,p in candidates.items()}
    # Equal weights are one candidate, not duplicate independent experiments.
    seen={};aliases={}
    for name,path in candidates.items():
        digest=weight_digest(actors[name].state_dict())
        if digest in seen:aliases[name]=seen[digest]
        else:seen[digest]=name
    candidates={n:p for n,p in candidates.items() if n not in aliases}
    if len(candidates)<2:raise ValueError('Need at least two distinct candidate model files')
    protocol={'candidates':{n:{'path':str(Path(p).resolve()),'sha256':sha256(p)} for n,p in candidates.items()},
              'rivals':{n:{'path':str(Path(p).resolve()),'sha256':sha256(p)} for n,p in rival_paths.items()},
              'seeds':seeds,'seconds':seconds,'scripted_kickoff_for_all_rivals':True,
              'rlbot_delay':True,'seed_base':seed_base}
    protocol['runtime']={name:version(name) for name in ('torch','rlgym-rocket-league','rocketsim')}
    protocol['code']={name:sha256(root/name) for name in (
        'slater_mechanics_eval.py','slater_mechanics_env.py','slater_mechanics_core.py',
        'slater_nexto_scheduler_v038b.py','slater_cycle9_native_ppo_v025.py',
        'afk_team_research.py','vendor/nexto/nexto_obs.py','nexto_teacher.py','slater_v041_worker.py')}
    if out.exists():raise FileExistsError(f'Comparison report already exists: {out}')
    state=read_json(partial,{'protocol':protocol,'records':[]})
    if state['protocol']!=protocol:raise RuntimeError('Comparison inputs/protocol changed; use a new output filename')
    actors={n:actors[n] for n in candidates}
    rivals={n:load_actor(root,p) for n,p in rival_paths.items()}
    done={(r['candidate'],r['rival'],r['side'],r['seed']) for r in state['records']}
    for j in range(seeds):
        seed=protocol['seed_base']+997*j
        for rival in rivals:
            for side in ('blue','orange'):
                for name,actor in actors.items():
                    key=(name,rival,side,seed)
                    if key in done:continue
                    row=full_match(actor,rivals,rival=rival,side=side,seed=seed,seconds=seconds)
                    row['candidate']=name;state['records'].append(row);done.add(key)
                    atomic_json(partial,state)
                    print('MECHANICS_COMPARE',name,rival,side,seed,
                          f"{row['goals_for']}:{row['goals_against']}",flush=True)
    ranking=[]
    for name in candidates:
        rows=[r for r in state['records'] if r['candidate']==name]
        ranking.append({'candidate':name,'matches':len(rows),'wins':sum(r['won'] for r in rows),
            'losses':sum(r['lost'] for r in rows),'draws':sum(r['draw'] for r in rows),
            'goals_for':sum(r['goals_for'] for r in rows),'goals_against':sum(r['goals_against'] for r in rows),
            'mean_goal_diff':float(np.mean([r['goal_diff'] for r in rows]))})
    ranking.sort(key=lambda r:(r['mean_goal_diff'],r['wins']-r['losses']),reverse=True)
    top=ranking[0]['candidate'];paired={}
    for other in candidates:
        if other==top:continue
        diffs=[]
        for j in range(seeds):
            seed=protocol['seed_base']+997*j
            by={n:np.mean([r['goal_diff'] for r in state['records'] if r['candidate']==n and r['seed']==seed]) for n in (top,other)}
            diffs.append(by[top]-by[other])
        paired[other]=interval(diffs)
    # Ranking selected the winner on these same samples. The intervals are
    # exploratory, not multiplicity-adjusted promotion evidence.
    distinct=seeds>=8 and all(v['lower'] is not None and v['lower']>0 for v in paired.values())
    result={**state,'aliases':aliases,'ranking':ranking,'paired_top_vs_others':paired,
            'recommended_source':str(Path(candidates[top]).resolve()),
            'recommended_source_sha256':sha256(candidates[top]),
            'selection_status':'PROVISIONAL_SCREEN_LEADER' if distinct else 'CLOSE_OR_INCONCLUSIVE',
            'note':'Matched simulator matches. Confirm finalists on fresh seeds/live offline matches; rank is not SSL evidence.'}
    for group in ('candidates','rivals'):
        for item in protocol[group].values():
            if sha256(item['path'])!=item['sha256']:raise RuntimeError('A comparison model changed during evaluation')
    atomic_json(out,result)
    print('MECHANICS_SELECTION',result['selection_status'],result['recommended_source'],flush=True)
    return result


def evaluate_stage(actor,rivals,stage,*,seeds,seed_base,seconds=6.):
    records=[]
    for j in range(seeds):
        seed=seed_base+997*j
        for rival in rivals:
            for side in ('blue','orange'):
                env=MechanicsEnv(rivals,stage=stage,difficulty=1.,max_seconds=seconds,
                                 fixed_side=side,fixed_rival=rival)
                try:
                    obs=env.reset(seed)
                    while True:
                        obs,_,done,info=env.step(greedy(actor,obs))
                        if done:
                            records.append({'seed':seed,'rival':rival,'side':side,**info});break
                finally:env.close()
    return {'records':records,'mastery':mastery_verdict(records)[1]}


def retention_check(actor,reference,rivals,*,seeds,seed_base,seconds,allowed_drop=.25):
    records=[];differences=[];by_rival={name:[] for name in rivals}
    for j in range(seeds):
        seed=seed_base+j*997;pair=[]
        for rival in rivals:
            rival_pair=[]
            for side in ('blue','orange'):
                candidate=full_match(actor,rivals,rival=rival,side=side,seed=seed,seconds=seconds)
                baseline=full_match(reference,rivals,rival=rival,side=side,seed=seed,seconds=seconds)
                delta=(candidate['goal_diff']-baseline['goal_diff'])*60/seconds
                pair.append(delta);rival_pair.append(delta)
                records.append({'candidate':candidate,'reference':baseline})
            by_rival[rival].append(float(np.mean(rival_pair)))
        differences.append(float(np.mean(pair)))
    ci=interval(differences)
    rival_intervals={name:interval(values) for name,values in by_rival.items()}
    ok=seeds>=4 and ci['lower'] is not None and ci['lower']>=-allowed_drop and all(
        row['lower'] is not None and row['lower']>=-allowed_drop for row in rival_intervals.values())
    return {'passed':ok,'paired_goal_diff_per_minute':ci,'per_rival':rival_intervals,
            'allowed_drop':allowed_drop,'records':records,
            'note':'A retention screen against initial source; full/live validation still required.'}
