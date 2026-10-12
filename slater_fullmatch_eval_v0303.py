r"""Slater v0.3.0.3 -- isolated-process, read-only multi-goal Nexto benchmark.

Runs *each* match in a separate Python interpreter, including original Cycle9
repeat checks. This isolates TorchScript, the native RocketSim library, and
per-process RNG state between policies. Reuses v0302 physics/game rules exactly.
Does not train, promote, or overwrite checkpoints. NOT identical to RLBot.

Example from Windows project root:
  .venv\Scripts\python.exe slater_fullmatch_eval_v0303.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v0303_smoke01.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

import numpy as np
import torch

import slater_fullmatch_eval_v0302 as fm
import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired
import slater_nexto_heldout_eval_v028 as heldout

MARKER='SLATER_V0303_WORKER_RESULT '
NEXTOSHA=paired.EXPECTED_NEXTO_SHA256


def protected_paths(root: Path):
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA
    source=root/CYCLE9
    nexto=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto)!=NEXTOSHA:
        raise RuntimeError('Original Cycle9 or Nexto SHA256 mismatch')
    return source, nexto, CYCLE9_SHA


def load_actor_and_nexto(root: Path, candidate: Path | None):
    from slater_research.checkpoint import cycle9_pair
    from nexto_teacher import nexto_actions
    torch.set_num_threads(2)
    source,nexto_path,sha=protected_paths(root)
    actor,orig=cycle9_pair(root)
    if candidate is None:
        model=orig
    else:
        path,doc=heldout.checked_candidate(str(candidate),root,sha,NEXTOSHA)
        meta=doc.get('meta',{})
        if meta.get('nexto_sha') != NEXTOSHA:
            raise RuntimeError('Candidate Nexto provenance missing / incorrect')
        actor.load_state_dict(doc['actor'],strict=True)
        model=actor
    model.eval()
    for p in model.parameters(): p.requires_grad_(False)
    nexto=torch.jit.load(str(nexto_path),map_location='cpu')
    nexto.eval()
    for p in nexto.parameters():p.requires_grad_(False)
    lookup=nexto_actions()
    actions=np.stack([np.asarray(lookup[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape!=(90,8) or not np.isfinite(actions).all():
        raise RuntimeError('Invalid Nexto action table')
    return model,nexto,actions


def worker_main(argv):
    p=argparse.ArgumentParser(description='Internal read-only single match worker')
    p.add_argument('--worker',action='store_true',required=True)
    p.add_argument('--policy',choices=('original','candidate'),required=True)
    p.add_argument('--candidate',default='')
    p.add_argument('--side',choices=('blue','orange'),required=True)
    p.add_argument('--match-seed',type=int,required=True)
    p.add_argument('--reg-steps',type=int,required=True)
    p.add_argument('--ot-steps',type=int,required=True)
    args=p.parse_args(argv)
    if args.policy=='candidate' and not args.candidate:
        p.error('candidate policy requires --candidate')
    if args.policy=='original' and args.candidate:
        p.error('original policy must not load a candidate')
    if not (1<=args.match_seed<2**31 and 1<=args.reg_steps<=4500 and 0<=args.ot_steps<=4500):
        p.error('invalid worker match parameters')
    root=Path.cwd().resolve()
    candidate=Path(args.candidate).resolve() if args.candidate else None
    actor,nexto,actions=load_actor_and_nexto(root,candidate)
    env=fm.IsolatedKickoffEnv(args.side,actions,nexto,args.reg_steps)
    try:
        row=fm.one_full_match(env,actor,args.match_seed,args.side,args.reg_steps,args.ot_steps)
    finally:
        env.close()
    protected_paths(root)
    print(MARKER+json.dumps(row,sort_keys=True),flush=True)


def parse_worker_stdout(stdout: str) -> dict:
    lines=[line[len(MARKER):] for line in stdout.splitlines() if line.startswith(MARKER)]
    if len(lines)!=1:
        raise RuntimeError(f'Worker returned {len(lines)} result markers; stdout tail: {stdout[-1000:]}')
    row=json.loads(lines[0])
    required={'seed','side','goals_for','goals_against','goal_diff','outcome',
              'draw','decisions','touches','opponent_touches','kickoffs',
              'first_kickoff_signature','overtime','goal_events'}
    if not isinstance(row,dict) or not required.issubset(row):
        raise ValueError('Worker result missing required fields')
    return row


def worker_command(script: Path, policy: str, candidate: Path | None, side: str,
                   seed: int, regulation_steps: int, overtime_steps: int) -> list[str]:
    if policy=='original' and candidate is not None:
        raise ValueError('Original must use original Cycle 9 weights')
    if policy!='original' and candidate is None:
        raise ValueError('Candidate path required')
    cmd=[sys.executable,str(script),'--worker','--policy',
         'original' if policy=='original' else 'candidate','--side',side,
         '--match-seed',str(seed),'--reg-steps',str(regulation_steps),
         '--ot-steps',str(overtime_steps)]
    if candidate is not None:cmd+=['--candidate',str(candidate)]
    return cmd


def request_subprocess(root:Path, script:Path, candidate_paths:dict[str,Path],
                       policy:str,side:str,seed:int,reg_steps:int,ot_steps:int)->dict:
    candidate=None if policy=='original' else candidate_paths[policy]
    cmd=worker_command(script,policy,candidate,side,seed,reg_steps,ot_steps)
    env=os.environ.copy()
    # Isolate CPU math library scheduling as much as possible.
    env.update(PYTHONHASHSEED='0', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1')
    try:
        proc=subprocess.run(cmd,cwd=str(root),env=env,capture_output=True,
                            text=True,timeout=300,check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Isolated worker timed out: policy={policy} side={side} seed={seed}') from exc
    if proc.returncode!=0:
        raise RuntimeError(f'Isolated worker failed policy={policy} side={side} seed={seed} '
                           f'exit={proc.returncode}\nSTDERR:\n{proc.stderr[-3000:]}\nSTDOUT:\n{proc.stdout[-1200:]}')
    row=parse_worker_stdout(proc.stdout)
    if row['seed']!=seed or row['side']!=side or row['decisions']>reg_steps+ot_steps:
        raise RuntimeError(f'Worker request/result mismatch: {row}')
    return row


def ensure_same(first:dict,repeat:dict,stage:str):
    if not fm.match_equal(first,repeat):
        differences={k:{'first':first.get(k),'repeat':repeat.get(k)}
                     for k in first if first.get(k)!=repeat.get(k)}
        raise RuntimeError('NONDETERMINISTIC_ISOLATED_MATCH '
                           +json.dumps({'stage':stage,'differences':differences},sort_keys=True))


def evaluate_processes(policy_names:list[str],seeds:int,seed_base:int,
                       reg_steps:int,ot_steps:int,request:Callable)->dict:
    """Injectable pure orchestration for offline reproducibility tests."""
    if 'original' not in policy_names or len(policy_names)!=len(set(policy_names)):
        raise ValueError('Need one original and unique candidate policy labels')
    records=[]
    baseline_probe={}
    for side in ('blue','orange'):
        first=request('original',side,seed_base,reg_steps,ot_steps)
        repeat=request('original',side,seed_base,reg_steps,ot_steps)
        ensure_same(first,repeat,'start '+side)
        baseline_probe[side]=first
    print('FRESH_PROCESS_INITIAL_REPEAT PASS (Blue + Orange)',flush=True)
    for i in range(seeds):
        seed=seed_base+997*i
        for side in ('blue','orange'):
            baseline=None
            for name in policy_names:
                row=request(name,side,seed,reg_steps,ot_steps)
                if baseline is not None and not fm.fingerprint_equal(row,baseline):
                    raise RuntimeError(f'UNMATCHED_KICKOFF seed={seed} side={side} policy={name}')
                if baseline is None:baseline=row
                records.append({'policy':name,**row})
        if (i+1)%2==0 or i+1==seeds:
            print(f'PROGRESS {i+1}/{seeds} seed pairs complete',flush=True)
    for side in ('blue','orange'):
        repeat=request('original',side,seed_base,reg_steps,ot_steps)
        ensure_same(baseline_probe[side],repeat,'after_candidates '+side)
    print('FRESH_PROCESS_FINAL_REPEAT PASS (Blue + Orange)',flush=True)
    overall={name:fm.aggregate([r for r in records if r['policy']==name]) for name in policy_names}
    by_side={name:{side:fm.aggregate([r for r in records if r['policy']==name and r['side']==side])
                   for side in ('blue','orange')} for name in policy_names}
    paired_results={name:fm.compare_by_seed(records,name) for name in policy_names if name!='original'}
    return {'overall':overall,'by_side':by_side,'paired_vs_original':paired_results,'records':records}


def parent_main(argv):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--extra',action='append',default=[])
    p.add_argument('--seeds',type=int,default=8)
    p.add_argument('--seed',type=int,default=1876359103)
    p.add_argument('--regulation-seconds',type=int,default=300)
    p.add_argument('--overtime-seconds',type=int,default=120)
    p.add_argument('--out',required=True)
    args=p.parse_args(argv)
    if not (2<=args.seeds<=128 and 1<=args.seed<2**31-128000
            and 10<=args.regulation_seconds<=300
            and 0<=args.overtime_seconds<=300 and len(args.extra)<=3):
        p.error('Invalid seed count, match lengths, or extra checkpoint count')
    root=Path.cwd().resolve()
    output=base.check_output(args.out,root,'.json')
    source,nexto,sha=protected_paths(root)
    paths={}
    provenance={}
    seen=set()
    for item in [args.checkpoint]+args.extra:
        path,doc=heldout.checked_candidate(item,root,sha,NEXTOSHA)
        if str(path) in seen:
            raise ValueError('Duplicate checkpoint')
        seen.add(str(path))
        meta=doc.get('meta',{})
        if meta.get('nexto_sha')!=NEXTOSHA:
            raise RuntimeError('Candidate Nexto provenance missing/mismatched')
        label='u'+str(doc['global_updates'])
        if label in paths:raise ValueError('Duplicate global update label')
        paths[label]=path
        provenance[label]={'source':str(path),'sha256':base.sha256(path),
                           'global_updates':doc['global_updates']}
    reg_steps=args.regulation_seconds*fm.FPS//fm.TICKS_PER_ACTION
    ot_steps=args.overtime_seconds*fm.FPS//fm.TICKS_PER_ACTION
    script=Path(__file__).resolve()
    def request(name,side,seed,r,ot):
        return request_subprocess(root,script,paths,name,side,seed,r,ot)
    started=time.perf_counter()
    print('ISOLATED_PROCESS_ROCKETSIM_MATCH_COMPARE read-only (one process per match)',flush=True)
    print('REGULATION',args.regulation_seconds,'s OVERTIME_CAP',args.overtime_seconds,
          's SEEDS',args.seeds,'BOTH_SIDES POLICIES',['original']+list(paths),flush=True)
    result=evaluate_processes(['original']+list(paths),args.seeds,args.seed,reg_steps,ot_steps,request)
    protected_paths(root)
    for name,path in paths.items():
        if base.sha256(path)!=provenance[name]['sha256']:
            raise RuntimeError('Candidate checkpoint changed mid-evaluation: '+name)
    report={'schema_version':3,
            'description':'Fresh Python interpreter per RocketSim match; still NOT equivalent to RLBot full matches.',
            'process_isolation':True,'match_repeat_checks':'start_and_finish_on_both_sides',
            'regulation_seconds':args.regulation_seconds,
            'overtime_cap_seconds':args.overtime_seconds,
            'seed_base':args.seed,'seed_count':args.seeds,'sides':2,
            'original_cycle9_sha256':sha,'nexto_sha256':NEXTOSHA,
            'candidates':provenance,
            'elapsed_seconds':round(time.perf_counter()-started,3),**result}
    print('OVERALL',json.dumps(result['overall'],sort_keys=True),flush=True)
    print('PAIRED_VS_ORIGINAL',json.dumps(result['paired_vs_original'],sort_keys=True),flush=True)
    print('BY_SIDE',json.dumps(result['by_side'],sort_keys=True),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print('SAVED_READ_ONLY_REPORT',output,'NO_CHECKPOINT_CHANGES',flush=True)


if __name__=='__main__':
    if '--worker' in sys.argv[1:]:worker_main(sys.argv[1:])
    else:parent_main(sys.argv[1:])
