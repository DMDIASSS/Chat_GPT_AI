"""Slater v0.3.0.4 -- independent, stochastic RocketSim comparison (READ ONLY).

Unlike deterministic integrity tests, this benchmark does NOT assume different
processes produce identical physical trajectories. It repeats policies on the
same seeded starting states and estimates uncertainty across seed pairs. Use it
for *statistical* performance comparisons ONLY. A failure in the separate
v0303 strict reproducibility guard is NOT silently reclassified as passing.

Not a replacement for RLBot evaluation, and not proof of generalization.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired
import slater_fullmatch_eval_v0302 as fm
import slater_fullmatch_eval_v0303 as workers
import slater_nexto_heldout_eval_v028 as heldout


def evaluate_stochastic(request, policy_names, seeds, repeats, seed_base, reg_steps, ot_steps):
    if 'original' not in policy_names or len(set(policy_names))!=len(policy_names):
        raise ValueError('One original policy and unique labels required')
    if not 2<=seeds<=256 or not 1<=repeats<=10:
        raise ValueError('Invalid sample size')
    records=[]
    for i in range(seeds):
        seed=seed_base+997*i
        for repeat in range(repeats):
            for side in ('blue','orange'):
                baseline=None
                for name in policy_names:
                    row=request(name,side,seed,reg_steps,ot_steps)
                    if baseline is not None and not fm.fingerprint_equal(row,baseline):
                        raise RuntimeError('UNMATCHED_STARTING_STATE '+str((seed,repeat,side,name)))
                    if baseline is None:baseline=row
                    records.append({'policy':name,'repeat':repeat,**row})
        print('BENCHMARK_PROGRESS',i+1,'/',seeds,'seed pairs',flush=True)
    overall={name:fm.aggregate([r for r in records if r['policy']==name]) for name in policy_names}
    by_side={name:{side:fm.aggregate([r for r in records if r['policy']==name and r['side']==side])
                   for side in ('blue','orange')} for name in policy_names}
    comparison={}
    for candidate in policy_names:
        if candidate=='original':continue
        per_seed={}
        for row in records:
            if row['policy'] in ('original',candidate):
                per_seed.setdefault((row['seed'],row['repeat'],row['side']),{})[row['policy']]=row
        samples={k:[] for k in ('win_rate','points_rate','goal_diff')}
        for seed in sorted({r['seed'] for r in records}):
            diffs={k:[] for k in samples}
            for repeat in range(repeats):
                for side in ('blue','orange'):
                    rows=per_seed[(seed,repeat,side)]
                    original=rows['original']; current=rows[candidate]
                    for name in diffs:
                        def score(r):
                            if name=='win_rate':return float(r['outcome']==1)
                            if name=='points_rate':return (1 if r['outcome']==1 else (.5 if r['outcome']==0 else 0))
                            return float(r['goal_diff'])
                        diffs[name].append(score(current)-score(original))
            for name in samples:samples[name].append(float(np.mean(diffs[name])))
        comparison[candidate]={name:paired.paired_interval(arr) for name,arr in samples.items()}
    return {'overall':overall,'by_side':by_side,'paired_vs_original':comparison,
            'records':records}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--extra',action='append',default=[])
    p.add_argument('--seeds',type=int,default=8)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--seed',type=int,default=1876359103)
    p.add_argument('--regulation-seconds',type=int,default=300)
    p.add_argument('--overtime-seconds',type=int,default=120)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    if not(2<=a.seeds<=128 and 2<=a.repeats<=5 and 1<=a.seed<2**31-128000
           and 10<=a.regulation_seconds<=300 and 0<=a.overtime_seconds<=300
           and len(a.extra)<=3):
        p.error('Invalid benchmark configuration')
    root=Path.cwd().resolve()
    output=base.check_output(a.out,root,'.json')
    source,nexto,sha=workers.protected_paths(root)
    paths={};provenance={}
    for filename in [a.checkpoint]+a.extra:
        path,doc=heldout.checked_candidate(filename,root,sha,workers.NEXTOSHA)
        if doc.get('meta',{}).get('nexto_sha')!=workers.NEXTOSHA:
            raise RuntimeError('Missing Nexto provenance')
        label='u'+str(doc['global_updates'])
        if label in paths:raise ValueError('Duplicate candidate label: '+label)
        paths[label]=path
        provenance[label]={'path':str(path),'sha256':base.sha256(path)}
    script=(root/'slater_fullmatch_eval_v0303.py').resolve()
    if not script.is_file():raise FileNotFoundError(script)
    def request(policy,side,seed,reg,ot):
        return workers.request_subprocess(root,script,paths,policy,side,seed,reg,ot)
    reg_steps=a.regulation_seconds*fm.FPS//fm.TICKS_PER_ACTION
    ot_steps=a.overtime_seconds*fm.FPS//fm.TICKS_PER_ACTION
    start=time.perf_counter()
    print('STOCHASTIC_ROCKETSIM_COMPARISON -- NOT A DETERMINISM PASS',flush=True)
    print('SEEDS',a.seeds,'REPEATS',a.repeats,'POLICIES',['original']+list(paths),flush=True)
    result=evaluate_stochastic(request,['original']+list(paths),a.seeds,a.repeats,a.seed,reg_steps,ot_steps)
    workers.protected_paths(root)
    for name,path in paths.items():
        if base.sha256(path)!=provenance[name]['sha256']:
            raise RuntimeError('Candidate checkpoint changed: '+name)
    report={'schema_version':4,'mode':'statistical_stochastic_comparison',
            'warning':'Does not establish deterministic physics; repeated matches may diverge even from identical starts. NOT RLBot full-match benchmark.',
            'regulation_seconds':a.regulation_seconds,
            'overtime_seconds':a.overtime_seconds,'seeds':a.seeds,'repeats':a.repeats,
            'seed_base':a.seed,'candidate_sha256':provenance,
            'original_cycle9_sha256':sha,'nexto_sha256':workers.NEXTOSHA,
            'elapsed_seconds':round(time.perf_counter()-start,2),**result}
    print('OVERALL',json.dumps(result['overall'],sort_keys=True),flush=True)
    print('PAIRED_VS_ORIGINAL',json.dumps(result['paired_vs_original'],sort_keys=True),flush=True)
    print('BY_SIDE',json.dumps(result['by_side'],sort_keys=True),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print('SAVED_STATISTICAL_BENCHMARK',output,'NO_CHECKPOINT_WRITES',flush=True)


if __name__=='__main__':main()
