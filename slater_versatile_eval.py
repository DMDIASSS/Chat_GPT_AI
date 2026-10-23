"""Resumable matched simulator evaluation with fresh screening/confirmation seeds."""
from pathlib import Path
import math
import time
import numpy as np
from slater_versatile_env import VersatileEnv
from slater_mechanics_eval import greedy,interval
from slater_v041_core import atomic_json,read_json


class EvaluationPaused(Exception):pass


def match(actor,rivals,*,rival,side,seed,seconds,task='match'):
    env=VersatileEnv(rivals,task_name=task,fixed_side=side,fixed_rival=rival,max_seconds=seconds,scripted_student=True)
    ticks=0;target=round(seconds*120);gf=ga=episodes=successes=scripts=0
    try:
        obs=env.reset(seed)
        while ticks<target:
            env.max_seconds=(env.tick_count+target-ticks)/120
            before=env.tick_count;obs,_,done,info=env.step(greedy(actor,obs));ticks+=env.tick_count-before
            if done:
                episodes+=1;gf+=info['outcome']==1;ga+=info['outcome']==-1;successes+=info['success'];scripts+=info['script_physics_ticks']
                if ticks<target:obs=env.reset(seed+7919*episodes)
    finally:env.close()
    return {'rival':rival,'side':side,'seed':seed,'task':task,'seconds':ticks/120,
            'goals_for':int(gf),'goals_against':int(ga),'goal_diff':int(gf-ga),
            'student_scripted_kickoff':True,'successes':int(successes),'episodes':episodes,'script_physics_ticks':scripts}


def sign_pvalue(values):
    # Ties are discarded. One paired mean across rivals/sides is one trial.
    nonzero=[v for v in values if abs(v)>1e-9];n=len(nonzero);wins=sum(v>0 for v in nonzero)
    return sum(math.comb(n,j) for j in range(wins,n+1))/2**n if n else 1.


def verdict(records,*,seeds,seconds,alpha,confirm):
    groups={};by_rival={}
    for row in records:
        c,r=row['candidate'],row['reference']
        delta=(c['goal_diff']-r['goal_diff'])*60/seconds
        groups.setdefault(c['seed'],[]).append(delta)
        by_rival.setdefault(c['rival'],{}).setdefault(c['seed'],[]).append(delta)
    required={(row['candidate']['rival'],side) for row in records for side in ('blue','orange')}
    cells={}
    for row in records:
        c,r=row['candidate'],row['reference'];key=(c['rival'],c['side'])
        if (c['rival'],c['side'],c['seed']) != (r['rival'],r['side'],r['seed']):raise ValueError('Unmatched evaluation records')
        parts=cells.setdefault(c['seed'],set())
        if key in parts:raise ValueError('Duplicate evaluation cell')
        parts.add(key)
    if not groups or any(parts!=required for parts in cells.values()):
        return {'passed':False,'reason':'incomplete_pairs'}
    diffs=[float(np.mean(v)) for v in groups.values()];ci=interval(diffs)
    per_rival={name:interval([float(np.mean(v)) for v in g.values()]) for name,g in by_rival.items()}
    p=sign_pvalue(diffs)
    passed=len(groups)==seeds and ci['mean']>0 and all(v['mean']>=-.25 for v in per_rival.values())
    if confirm:passed &= seeds>=8 and p<=alpha and ci['lower'] is not None and ci['lower']>0 and all(v['lower'] is not None and v['lower']>=-.5 for v in per_rival.values())
    return {'passed':bool(passed),'paired_goal_diff_per_minute':ci,'per_rival':per_rival,
            'one_sided_sign_p':p,'alpha':alpha,'confirmed':bool(confirm),
            'note':'Simulator evidence with matched seed clusters, not an SSL rank or live export guarantee.'}


def evaluate(candidate,reference,rivals,*,out,identity,seeds,seconds,seed_base,alpha=.05,confirm=False,pause_path=None):
    out=Path(out);protocol={**identity,'student_scripted_kickoff':True,'seeds':seeds,'seconds':seconds,'seed_base':seed_base,'alpha':alpha,'confirm':confirm}
    state=read_json(out,{'protocol':protocol,'records':[],'done':False})
    if state['protocol']!=protocol:raise ValueError('Evaluation inputs changed; refuse cached scores')
    if state['done']:return state
    done={(r['candidate']['rival'],r['candidate']['side'],r['candidate']['seed']) for r in state['records']}
    total=seeds*len(rivals)*2;started=time.perf_counter();new=0
    print('VERSATILE_EVAL_BEGIN',out.stem,'completed_pairs',len(done),'total_pairs',total,
          'remaining_simulated_minutes',round((total-len(done))*seconds*2/60,1),flush=True)
    for j in range(seeds):
        for rival in rivals:
            for side in ('blue','orange'):
                seed=seed_base+997*j;key=(rival,side,seed)
                if key in done:continue
                if pause_path and Path(pause_path).exists():raise EvaluationPaused()
                c=match(candidate,rivals,rival=rival,side=side,seed=seed,seconds=seconds)
                r=match(reference,rivals,rival=rival,side=side,seed=seed,seconds=seconds)
                state['records'].append({'candidate':c,'reference':r});new+=1
                atomic_json(out,state)
                eta=(time.perf_counter()-started)/new*(total-len(state['records']))
                print('VERSATILE_EVAL',out.stem,len(state['records']),'/',total,rival,side,
                      f"candidate {c['goals_for']}:{c['goals_against']} reference {r['goals_for']}:{r['goals_against']}",
                      'eta_minutes',round(eta/60,1),flush=True)
    state['verdict']=verdict(state['records'],seeds=seeds,seconds=seconds,alpha=alpha,confirm=confirm)
    state['done']=True;atomic_json(out,state);return state


def skill_guard(candidate,reference,rivals,*,out,identity,seed_base,seeds=4,seconds=8,pause_path=None):
    out=Path(out);protocol={**identity,'seed_base':seed_base,'seeds':seeds,'seconds':seconds}
    state=read_json(out,{'protocol':protocol,'records':[]})
    if state['protocol']!=protocol:raise ValueError('Skill guard inputs changed')
    done={(r['task'],r['seed'],r['side']) for r in state['records']}
    rival=next(iter(rivals))
    for task in ('defense','recovery','aerial','teamplay'):
        for j in range(seeds):
            for side in ('blue','orange'):
                seed=seed_base+997*j
                if (task,seed,side) in done:continue
                if pause_path and Path(pause_path).exists():raise EvaluationPaused()
                pair=[match(a,rivals,rival=rival,side=side,seed=seed,seconds=seconds,task=task) for a in (candidate,reference)]
                state['records'].append({'task':task,'seed':seed,'side':side,'candidate':pair[0],'reference':pair[1]})
                atomic_json(out,state)
    guards={}
    for task in ('defense','recovery','aerial','teamplay'):
        rows=[r for r in state['records'] if r['task']==task]
        delta=float(np.mean([r['candidate']['successes']/max(1,r['candidate']['episodes'])-r['reference']['successes']/max(1,r['reference']['episodes']) for r in rows]))
        gd=float(np.mean([(r['candidate']['goal_diff']-r['reference']['goal_diff'])*60/seconds for r in rows]))
        guards[task]={'success_delta':delta,'goal_diff_delta_per_minute':gd,'passed':delta>=-.125 and gd>=-.5}
    state['guards']=guards;state['passed']=all(r['passed'] for r in guards.values());atomic_json(out,state)
    print('VERSATILE_SKILL_GUARD',state['passed'],guards,flush=True);return state
