"""Automatic first-goal screening and a separately retained deployment champion.

These screens reduce unattended regression risk; they are not full-match proof
or a statistical guarantee over an unlimited sequence of promotion decisions.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import uuid
import numpy as np
import torch
from .core import atomic_json,check_model,sha256
from .chronos import CHRONOS_CONTRACT,ChronosEnv


class EvaluationStopped(Exception):pass


def select_checkpoint(run,*,initial=False,latest=False):
    from .chronos_training import resolve_chronos
    run=Path(run).resolve()
    if initial:return resolve_chronos(run/'checkpoints/step_000000000000.zip')
    if latest:return resolve_chronos(run)
    record=json.loads((run/'champion.json').read_text()) if (run/'champion.json').exists() else {'path':'checkpoints/step_000000000000.zip'}
    path=(run/record['path']).resolve()
    if not path.is_relative_to(run):raise ValueError('Champion path escapes its run')
    return resolve_chronos(path)


def ensure_champion(run):
    run=Path(run)
    if (run/'champion.json').exists():
        select_checkpoint(run);return
    initial=run/'checkpoints/step_000000000000.zip'
    meta=check_model(initial,CHRONOS_CONTRACT)
    cfg=json.loads((run/'config.json').read_text()) if (run/'config.json').exists() else {}
    origin='Selected trained Fusion initialization' if cfg.get('fusion_refinement') else 'Unchanged Chronos initialization'
    atomic_json(run/'champion.json',dict(path=str(initial.relative_to(run)),timesteps=0,
        sha256=meta['sha256'],reason=origin+'; no unverified promotion'))


def paired_statistics(rows,baseline):
    def key(r):return (r['opponent'],r['scenario'],int(r['seed']),int(r['side']))
    other={key(r):r for r in baseline}
    if len(other)!=len(baseline) or len(rows)!=len(baseline) or len({key(r) for r in rows})!=len(rows):raise ValueError('Unpaired screening rows')
    blocks={};by_opponent={}
    for row in rows:
        k=key(row)
        if k not in other:raise ValueError('Unpaired screening seed/side')
        block=k[:3];difference=float(row['outcome']-other[k]['outcome'])
        blocks.setdefault(block,[]).append(difference)
        by_opponent.setdefault(k[0],[]).append(difference)
    if any(len(v)!=2 for v in blocks.values()):raise ValueError('Each seed block needs both team sides')
    values=np.array([np.mean(v) for v in blocks.values()],dtype=float)
    return dict(blocks=len(values),trials=len(rows),mean_delta=float(values.mean()),
        standard_error=float(values.std(ddof=1)/len(values)**.5) if len(values)>1 else None,
        by_opponent_delta={k:float(np.mean(v)) for k,v in by_opponent.items()})


def judgement(stats,settings):
    se=stats['standard_error']
    if se is None:return 'retain'
    lower=stats['mean_delta']-settings['z']*se
    upper=stats['mean_delta']+settings['z']*se
    if (stats['mean_delta']>=settings['min_delta'] and lower>0 and
        min(stats['by_opponent_delta'].values())>=-settings['per_opponent_tolerance']):return 'improved'
    if upper < -settings['min_delta']:return 'regressed'
    return 'retain'


def practice_screen(cfg,candidate,baseline,pairs,seconds,seed,stop_path):
    """Both team colors share a seed block; cells receive distinct seeds."""
    from .chronos_training import ChronosRunner
    if Path(stop_path).exists():raise EvaluationStopped()
    cfg=json.loads(json.dumps(cfg));cfg['curriculum']['adaptive']=False
    cfg['env'].update(episode_seconds=seconds,no_touch_seconds=seconds+1)
    policies=[ChronosRunner(candidate),ChronosRunner(baseline)]
    rows=[[],[]]
    for cell,(opponent,scenario) in enumerate((o,s) for o in ('chronos','galactus','nexto','ripple') for s in ('kickoff','shot','defense')):
        for pair in range(pairs):
            episode_seed=int(seed+cell*100000+pair)
            for side in (0,1):
                env=ChronosEnv(cfg,opponent=opponent,scenario=scenario,side=side)
                try:
                    initial=None
                    for index,policy in enumerate(policies):
                        obs,_=env.reset(seed=episode_seed)
                        if initial is None:initial=obs.copy()
                        elif not np.array_equal(initial,obs):raise RuntimeError('Automatic comparison has different starting observations')
                        while True:
                            if Path(stop_path).exists():raise EvaluationStopped()
                            obs,_,terminal,truncated,info=env.step(policy.action(obs))
                            if terminal or truncated:break
                        rows[index].append({k:info[k] for k in ('opponent','scenario','side','outcome','touches','timeout','practice_success')})
                        rows[index][-1]['seed']=episode_seed
                finally:env.close()
        print(f'AUTO_CHECK {opponent}/{scenario} complete',flush=True)
    return rows[0],rows[1]


def screen(cfg,candidate,baseline,pairs,seconds,seed,stop_path):
    from .chronos_league import match_suite
    return match_suite(cfg,candidate,baseline,pairs,seconds,seed,stop_path)


def promote(run,source,statistics):
    run=Path(run);meta=check_model(source,CHRONOS_CONTRACT)
    folder=run/'champions'/f'candidate_{meta["timesteps"]:012d}_{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    destination=folder/'full.zip'
    shutil.copy2(source,destination);shutil.copy2(str(source)+'.json',str(destination)+'.json')
    check_model(destination,CHRONOS_CONTRACT)
    atomic_json(run/'champion.json',dict(path=str(destination.relative_to(run)),sha256=meta['sha256'],
        timesteps=meta['timesteps'],statistics=statistics,reason='Passed screen and fresh-seed confirmation against retained champion'))
    # Retain the current and previous promoted generations; step-0 stays separate.
    for old in sorted((run/'champions').glob('candidate_*'),key=lambda p:p.stat().st_mtime,reverse=True)[2:]:
        if old.is_dir() and not old.is_symlink():shutil.rmtree(old)


def reset_critic(model,warmup):
    for module in model.policy.value_net.modules():
        if hasattr(module,'reset_parameters'):module.reset_parameters()
    with torch.no_grad():
        model.policy.value_net[-1].weight.zero_();model.policy.value_net[-1].bias.zero_()
    model.policy.optimizer.state.clear()
    model.critic_warmup_updates=model.chronos_updates+warmup


def check_progress(run,cfg,model,tracker,*,force=False):
    from .chronos_training import resolve_chronos,load_network
    from .chronos_league import match_summary
    run=Path(run);settings=cfg['chronos'].get('guard',{})
    if not settings.get('enabled'):return False
    ensure_champion(run)
    path=run/'guard_state.json';state=json.loads(path.read_text()) if path.exists() else {}
    step=int(model.num_timesteps)
    if not force and step-state.get('last_checked_step',0)<settings['every']:return False
    if (run/'STOP').exists():return False
    candidate=resolve_chronos(run);champion=select_checkpoint(run)
    serial=state.get('checks',0)
    # Rotating development screens, then an independent confirmation seed bank.
    seed=settings['seed']+serial*10000000
    rows,baseline=screen(cfg,candidate,champion,settings['pairs'],settings['seconds'],seed,run/'STOP')
    stats=paired_statistics(rows,baseline);decision=judgement(stats,settings)
    confirmed=False
    if decision=='improved':
        fresh,old=screen(cfg,candidate,champion,settings['confirmation_pairs'],settings['seconds'],seed+5000000,run/'STOP')
        confirmed=judgement(paired_statistics(fresh,old),settings)=='improved'
        rows+=fresh;baseline+=old;stats=paired_statistics(rows,baseline)
        if not confirmed:decision='retain'
    report=dict(kind='chronos_timed_matches',candidate_sha256=sha256(candidate),baseline_sha256=sha256(champion),
        summary=match_summary(rows),baseline_summary=match_summary(baseline),statistics=stats,decision=decision,
        confirmation_passed=confirmed,paired_initial_observations_verified=True,seed_start=seed,
        note='Team colors are clustered by seeded start. Timed multi-goal simulator matches; level scores are draws. Goal pauses/overtime omitted.')
    out=run.parent.parent/'reports'/f'{run.name}_auto_{step:012d}_{uuid.uuid4().hex[:6]}.json'
    atomic_json(out,report)
    rollback=False
    if decision=='improved' and confirmed:
        promote(run,candidate,stats);state['regressions']=0
    elif decision=='regressed':state['regressions']=state.get('regressions',0)+1
    else:state['regressions']=0
    severe=(decision=='regressed' and stats['mean_delta']<=-.35)
    if severe or state.get('regressions',0)>=settings['rollback_after']:
        model.policy.actor.load_state_dict(load_network(champion).state_dict())
        reset_critic(model,cfg['chronos']['critic_warmup_updates'])
        model.actor_lr=max(model.actor_lr*.5,1e-7);model.anchor_coef=min(model.anchor_coef*1.5,4.)
        state['regressions']=0;state['rollbacks']=state.get('rollbacks',0)+1;rollback=True
        state['halt_reason']='Substantial match regression against retained champion'
        model.training_halt_reason=state['halt_reason']
        (run/'STOP').touch()
    state.update(last_checked_step=step,checks=serial+1,decision=decision,statistics=stats,
        champion_sha256=sha256(select_checkpoint(run)),champion_timesteps=check_model(select_checkpoint(run),CHRONOS_CONTRACT)['timesteps'])
    state['candidate_wdl']=match_summary(rows);state['champion_wdl']=match_summary(baseline)
    atomic_json(path,state)
    with (run/'guard_history.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(state)+'\n')
    tracker.log({'guard/mean_outcome_delta':stats['mean_delta'],'guard/promoted':int(decision=='improved' and confirmed),
        'guard/rolled_back':int(rollback),'guard/champion_timesteps':state['champion_timesteps']},step)
    print('AUTO_CHECK_RESULT:',decision,'champion at',state['champion_timesteps'],'decisions',flush=True)
    return rollback
