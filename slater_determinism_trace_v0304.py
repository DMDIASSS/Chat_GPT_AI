"""Slater v0.3.0.4 -- read-only cross-process *first divergence* diagnostic.

Does not perform a win-rate evaluation, write checkpoints, or alter the PPO
campaign. Each trace uses a brand-new Python process, TorchScript model,
observer, and RocketSim arena. Records observation, policy action, actual
opponent control, simulator-state hashes and touch counters at each decision.

Run from the project's Windows root:
  .venv\\Scripts\\python.exe slater_determinism_trace_v0304.py --steps 300 --runs 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np

import slater_fullmatch_eval_v0302 as fm
import slater_fullmatch_eval_v0303 as workerlib
import slater_cycle9_paired_eval_v026_fixed as paired

MARKER = 'SLATER_TRACE_V0304 '
FIELDS = ('before_obs', 'before_state', 'student_action', 'opponent_command',
          'after_obs', 'after_state', 'student_touches', 'opponent_touches', 'outcome')


def hash_numpy(values: Any) -> str:
    h=hashlib.sha256()
    if isinstance(values,(tuple,list)):
        for part in values:
            a=np.ascontiguousarray(part,dtype='<f4')
            h.update(str(a.shape).encode('ascii'))
            h.update(a.tobytes())
    else:
        a=np.ascontiguousarray(values,dtype='<f4')
        h.update(str(a.shape).encode('ascii'))
        h.update(a.tobytes())
    return h.hexdigest()[:20]


def collect_trace(side: str, seed: int, steps: int, mode: str, actor, nexto, actions) -> dict:
    env=fm.IsolatedKickoffEnv(side,actions,nexto,max_steps=steps)
    try:
        obs, start_hash=fm.seeded_reset(env,fm.kickoff_seed(seed,0))
        start_obs=hash_numpy(obs)
        records=[]
        opposite='orange-0' if side=='blue' else 'blue-0'
        for tick in range(steps):
            before_state=fm.detailed_kickoff_signature(env)
            before_obs=hash_numpy(obs)
            chosen=0 if mode=='fixed_action_0' else paired.greedy_action(actor,obs,'cpu')
            obs,_,done,info=env.step(chosen)
            controls=hash_numpy(env.previous[opposite])
            row={'step':tick+1,'before_state':before_state,
                 'before_obs':before_obs, 'student_action':chosen,
                 'opponent_command':controls,
                 'after_state':fm.detailed_kickoff_signature(env),
                 'after_obs':hash_numpy(obs),
                 'student_touches':int(info['student_touches']),
                 'opponent_touches':int(info['opponent_touches']),
                 'outcome':int(info['outcome'])}
            records.append(row)
            if done: break
        return {'side':side,'mode':mode,'match_seed':seed,'start_state':start_hash,
                'start_obs':start_obs,'records':records}
    finally:
        env.close()


def first_divergence(reference:dict, other:dict)->dict|None:
    for k in ('side','mode','match_seed','start_state','start_obs'):
        if reference[k]!=other[k]:
            return {'stage':'initial','field':k,'expected':reference[k],'observed':other[k]}
    for i,(a,b) in enumerate(zip(reference['records'],other['records'])):
        different={k:{'expected':a[k],'observed':b[k]} for k in FIELDS if a[k]!=b[k]}
        if different:
            return {'stage':'step','step':i+1,'differences':different,
                    'first_unmatched_field':next(iter(different))}
    if len(reference['records'])!=len(other['records']):
        return {'stage':'length','expected':len(reference['records']),
                'observed':len(other['records'])}
    return None


def classify_divergence(diff:dict|None)->str:
    if diff is None: return 'exactly reproducible for tested decisions'
    if diff['stage']=='initial':return 'reset / initial observation mismatch'
    if diff['stage']=='length':return 'different episode termination'
    keys=set(diff['differences'])
    if 'before_state' in keys:
        return 'physics state already different before this decision (look at prior step)'
    if 'before_obs' in keys:
        return 'observation differs before action; inspect observer/state transition'
    if 'student_action' in keys:
        return 'student selects different action on matching observations'
    if 'opponent_command' in keys:
        return 'opponent selects different controls on matching earlier state'
    if 'after_state' in keys:
        return 'RocketSim state differs after the decision; inspect control and native physics'
    if 'after_obs' in keys:
        return 'observation differs despite matching state fingerprint'
    if 'student_touches' in keys or 'opponent_touches' in keys:
        return 'touch accounting differs while recorded physics state matches'
    return 'outcome differs'


def worker_args(parser,flag):
    parser.add_argument(flag,action='store_true')
    parser.add_argument('--side',choices=('blue','orange'))
    parser.add_argument('--mode',choices=('greedy','fixed_action_0'))
    parser.add_argument('--seed',type=int,default=1876359103)
    parser.add_argument('--steps',type=int,default=300)


def run_child(argv:list[str])->None:
    p=argparse.ArgumentParser(description=__doc__)
    worker_args(p,'--child')
    a=p.parse_args(argv)
    if a.side is None or a.mode is None or not(1<=a.steps<=9000 and 1<=a.seed<2**31):
        p.error('Invalid child trace parameters')
    actor,nexto,actions=workerlib.load_actor_and_nexto(Path.cwd().resolve(),None)
    trace=collect_trace(a.side,a.seed,a.steps,a.mode,actor,nexto,actions)
    workerlib.protected_paths(Path.cwd().resolve())
    print(MARKER+json.dumps(trace,separators=(',',':')),flush=True)


def child_command(script:Path,side:str,mode:str,seed:int,steps:int)->list[str]:
    if side not in ('blue','orange') or mode not in ('greedy','fixed_action_0'):
        raise ValueError('Invalid trace configuration')
    return [sys.executable,str(script),'--child','--side',side,'--mode',mode,
            '--seed',str(seed),'--steps',str(steps)]


def request_trace(script:Path, root:Path, side:str,mode:str,seed:int,steps:int)->dict:
    cmd=child_command(script,side,mode,seed,steps)
    env=os.environ.copy()
    env.update(PYTHONHASHSEED='0',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    proc=subprocess.run(cmd,cwd=str(root),env=env,capture_output=True,text=True,
                        timeout=240,check=False)
    if proc.returncode:
        raise RuntimeError('Trace worker failed: '+proc.stderr[-2500:]+proc.stdout[-800:])
    lines=[line[len(MARKER):] for line in proc.stdout.splitlines() if line.startswith(MARKER)]
    if len(lines)!=1:
        raise RuntimeError('Expected exactly one trace marker, found '+str(len(lines)))
    trace=json.loads(lines[0])
    if (trace['side'],trace['mode'],trace['match_seed'])!=(side,mode,seed):
        raise RuntimeError('Trace request mismatch')
    return trace


def parent_main(argv:list[str])->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--steps',type=int,default=300)
    p.add_argument('--runs',type=int,default=4)
    p.add_argument('--seed',type=int,default=1876359103)
    a=p.parse_args(argv)
    if not(30<=a.steps<=4500 and 2<=a.runs<=10 and 1<=a.seed<2**31):
        p.error('steps 30..4500, runs 2..10, positive seed')
    root=Path.cwd().resolve();script=Path(__file__).resolve()
    print('TRACE_ONLY fresh Python process per trace; no checkpoints written',flush=True)
    print('CONFIG',json.dumps({'match_seed':a.seed,'steps':a.steps,'runs':a.runs}),flush=True)
    nonreproducible=0
    for side in ('blue','orange'):
        for mode in ('fixed_action_0','greedy'):
            original=request_trace(script,root,side,mode,a.seed,a.steps)
            mismatch=None
            for run in range(2,a.runs+1):
                another=request_trace(script,root,side,mode,a.seed,a.steps)
                mismatch=first_divergence(original,another)
                if mismatch is not None: break
            result={'side':side,'mode':mode,'deterministic':mismatch is None,
                    'runs_checked':run,'steps_reference':len(original['records']),
                    'first_divergence':mismatch,
                    'diagnosis':classify_divergence(mismatch)}
            print('CROSS_PROCESS_TRACE',json.dumps(result,sort_keys=True),flush=True)
            if mismatch is not None:nonreproducible+=1
    workerlib.protected_paths(root)
    print('TRACE_COMPLETE',json.dumps({'nonreproducible_cases':nonreproducible,
          'total_cases':4,'checkpoint_writes':0}),flush=True)


if __name__=='__main__':
    if '--child' in sys.argv[1:]:run_child(sys.argv[1:])
    else:parent_main(sys.argv[1:])
