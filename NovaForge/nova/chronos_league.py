"""Timed multi-goal Soccar matches with real W/D/L (draws are level scores)."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import uuid
import time
import numpy as np
from .chronos import ChronosEnv,CHRONOS_CONTRACT
from .core import ROOT,atomic_json,sha256
from .training import load_config


def match_summary(rows):
    return dict(matches=len(rows),wins=sum(r['outcome']>0 for r in rows),draws=sum(r['outcome']==0 for r in rows),
        losses=sum(r['outcome']<0 for r in rows),goals_for=sum(r.get('goals_for',0) for r in rows),
        goals_against=sum(r.get('goals_against',0) for r in rows))


def play_match(cfg,policy,opponent,side,seed,seconds,stop_path,progress=None):
    from .chronos_guard import EvaluationStopped
    cfg=copy.deepcopy(cfg);cfg['curriculum']['adaptive']=False
    if tuple(cfg.get('selector_experts',()))==('chronos','galactus','fusion','ducky','rain','megabyte'):
        cfg['env']['fusion_opponent']=str(policy.gate.fusion_path)
    ticks=0;goals_for=0;goals_against=0;contacts=0;point=0
    initial_hash=None
    match_ticks=int(round(seconds*120/8))*8
    started=time.monotonic();last_notice=started
    if match_ticks<8:raise ValueError('Match duration must be at least one decision')
    while ticks<match_ticks:
        if Path(stop_path).exists():raise EvaluationStopped()
        cfg['env'].update(episode_seconds=(match_ticks-ticks)/120,no_touch_seconds=(match_ticks+8)/120)
        env=ChronosEnv(cfg,opponent=opponent,scenario='kickoff',side=side)
        try:
            obs,_=env.reset(seed=seed+point*1000003)
            if initial_hash is None:initial_hash=hashlib.sha256(obs.tobytes()).hexdigest()
            if hasattr(policy,'bind'):policy.bind(env)
            while True:
                if Path(stop_path).exists():raise EvaluationStopped()
                if hasattr(policy,'step_env'):obs,_,terminal,truncated,info=policy.step_env(env,obs)
                elif hasattr(policy,'world_controls'):obs,_,terminal,truncated,info=env.step_world_controls(policy.world_controls(obs))
                else:obs,_,terminal,truncated,info=env.step(policy.action(obs))
                ticks+=8
                now=time.monotonic()
                if progress is not None and now-last_notice>=5:
                    progress(dict(event='heartbeat',simulated_seconds=ticks/120,seconds=match_ticks/120,
                        goals_for=goals_for,goals_against=goals_against,wall_seconds=now-started))
                    last_notice=now
                if terminal or truncated:break
            contacts+=info['touches']
            if terminal:
                goals_for+=int(info['outcome']>0);goals_against+=int(info['outcome']<0)
        finally:env.close()
        point+=1
    result=dict(opponent=opponent,scenario='match',seed=seed,side=side,seconds=match_ticks/120,
        goals_for=goals_for,goals_against=goals_against,outcome=int(np.sign(goals_for-goals_against)),
        touches=contacts,timeout=False,practice_success=goals_for>goals_against)
    result['initial_observation_sha256']=initial_hash
    return result


def match_suite(cfg,candidate,baseline,pairs,seconds,seed,stop_path):
    from .chronos_training import ChronosRunner
    from .chronos_guard import EvaluationStopped
    if Path(stop_path).exists():raise EvaluationStopped()
    opponents=tuple(cfg.get('selector_evaluation_opponents',('chronos','galactus','nexto','ripple')))
    total=len(opponents)*pairs*2*2;completed=0;started=time.monotonic()
    print(f'WDL_START: {total} games, {seconds:g} simulated seconds each; both team colors. Ctrl+C cancels.',flush=True)
    print('WDL_LOADING: candidate and baseline controllers',flush=True)
    a=candidate if hasattr(candidate,'action') or hasattr(candidate,'world_controls') else ChronosRunner(candidate)
    b=baseline if hasattr(baseline,'action') or hasattr(baseline,'world_controls') else ChronosRunner(baseline)
    rows=[];old=[]
    for cell,opponent in enumerate(opponents):
        for pair in range(pairs):
            game_seed=seed+cell*100000+pair
            for side in (0,1):
                for label,policy,destination in [('candidate',a,rows),('baseline',b,old)]:
                    prefix=f'GAME {completed+1}/{total} {label} vs {opponent} side={side} seed={game_seed}'
                    print(prefix+' START (loading arena/opponent)',flush=True)
                    def heartbeat(event):
                        print(prefix+f' RUNNING {event["simulated_seconds"]:.1f}/{event["seconds"]:.1f}s score={event["goals_for"]}:{event["goals_against"]} elapsed={event["wall_seconds"]:.0f}s',flush=True)
                    result=play_match(cfg,policy,opponent,side,game_seed,seconds,stop_path,progress=heartbeat)
                    destination.append(result);completed+=1
                    print(prefix+f' DONE score={result["goals_for"]}:{result["goals_against"]} total_elapsed={time.monotonic()-started:.0f}s',flush=True)
                if rows[-1]['initial_observation_sha256']!=old[-1]['initial_observation_sha256']:
                    raise RuntimeError('Timed match initial observations differ')
        print('MATCHES',opponent,'candidate',match_summary([r for r in rows if r['opponent']==opponent]),
            'baseline',match_summary([r for r in old if r['opponent']==opponent]),flush=True)
    return rows,old


def league_command(args):
    import torch
    torch.set_num_threads(1)
    from filelock import FileLock
    from .chronos_guard import select_checkpoint,paired_statistics
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve():raise ValueError('Invalid run name')
    with FileLock(str(run/'train.lock'),timeout=0):
        candidate=select_checkpoint(run,latest=getattr(args,'latest',False));baseline=select_checkpoint(run,initial=True)
        cfg=load_config(run/'config.json')
        if getattr(args,'ensemble',False):
            from .chronos_fusion import FusionRunner
            policy=FusionRunner();candidate_hash='experimental_teacher_probability_ensemble_50_25_25'
        else:policy=candidate;candidate_hash=sha256(candidate)
        rows,old=match_suite(cfg,policy,baseline,args.pairs,args.seconds,args.seed,run/'LEAGUE_STOP')
        output=ROOT/'reports'/f'{args.run}_wdl_{uuid.uuid4().hex[:10]}.json'
        atomic_json(output,dict(kind='chronos_timed_matches',contract=CHRONOS_CONTRACT,candidate_sha256=candidate_hash,
            baseline_sha256=sha256(baseline),summary=match_summary(rows),baseline_summary=match_summary(old),
            statistics=paired_statistics(rows,old),trials=rows,baseline_trials=old,
            note='Timed multi-goal simulator games from standard kickoffs. Level scores are draws. Goal pauses/overtime are omitted; this is not a live RLBot match.'))
        print('WDL_REPORT_READY:',output,flush=True)
