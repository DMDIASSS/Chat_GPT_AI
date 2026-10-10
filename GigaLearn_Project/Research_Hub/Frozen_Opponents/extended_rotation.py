"""Checkpoint-safe, multi-round 1v1 rotation: Nexto -> Cycle9 -> Wavedash.

Built on top of the *already smoke-tested* frozen_cli.py + isolated worker.
No PyTorch imports, no original checkpoint writes, no automatic promotion.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
HUB = HERE.parent
EXPERIMENTS = HUB / 'experiments'
BASELINE = 'nexto_rotation_01'
CHALLENGER = 'tri_teacher_challenger_01'
ROTATION = 65536
STEP_BLOCK = 3 * ROTATION
STATE_FILE = 'extended_rotation_state.json'
OWN_MARK = 'GIGALEARN_EXTENDED_TRI_TEACHER_V1'
TEACHERS = ('nexto', 'cycle9', 'wavedash')


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    try:
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def checkpoints(exp: Path):
    cpdir = exp / 'checkpoints'
    if not cpdir.is_dir():
        return []
    return sorted([p for p in cpdir.iterdir() if p.is_dir() and p.name.isdecimal()],key=lambda x:int(x.name))


def latest(exp: Path):
    cps=checkpoints(exp)
    if not cps: raise RuntimeError('Missing checkpoints for ' + str(exp))
    cp=cps[-1]
    for name in ('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json'):
        if not (cp / name).is_file() or (cp / name).stat().st_size==0:
            raise RuntimeError('Incomplete checkpoint: '+str(cp/name))
    return cp


def validate_setup():
    cli=HERE/'frozen_cli.py'
    worker=HERE/'frozen_nexto_bridge.py'
    patch=HERE/'extended_frozen_cli_patch.py'
    for file in (cli,worker,patch):
        if not file.is_file(): raise FileNotFoundError('Missing required file: '+str(file))
    source=cli.read_text(encoding='utf-8-sig')
    if 'GL_EXTENDED_SAVE_CONFIG_V1' not in source:
        raise RuntimeError('Run 0_SETUP_EXTENDED.bat first to enable safe save intervals')
    if 'FROZEN_WORKER_SUBPROCESS_V1' not in source or 'FROZEN_DLL_BUILD_GUARD_V1' not in source:
        raise RuntimeError('Existing isolated-worker or DLL-guard fix missing: please install those fixes first')
    if 'FROZEN_WORKER_ISOLATION_V1' not in worker.read_text(encoding='utf-8-sig'):
        raise RuntimeError('Torch-isolation worker not installed')
    # No Torch import in the controlling process.
    import frozen_cli
    frozen_cli.verify_install()
    teachers=frozen_cli.resolve_teachers(argparse.Namespace(nexto=frozen_cli.DEFAULT_NEXTO,
                                  cycle9=frozen_cli.DEFAULT_CYCLE9,wavedash=frozen_cli.DEFAULT_WAVEDASH))
    return teachers


def _state_path(exp):return exp/STATE_FILE


def init_challenger(name=CHALLENGER, baseline=BASELINE, *, seed=None):
    exp=EXPERIMENTS/name
    state_path=_state_path(exp)
    if exp.exists():
        if not state_path.is_file():
            raise RuntimeError('Experiment exists without our journal; refusing to take ownership: '+str(exp))
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('kind')!=OWN_MARK or state.get('experiment')!=name:
            raise RuntimeError('Unexpected experiment state; refusing to modify '+str(exp))
        return state
    import frozen_cli
    if seed:
        cp=frozen_cli.verify_seed(Path(seed).resolve())
    else:
        baseline_exp=EXPERIMENTS/baseline
        cp=latest(baseline_exp)
        if int(cp.name)==0:
            raise RuntimeError('Starting branch is still at checkpoint 0. Complete teacher smoke tests first')
    args=argparse.Namespace(name=name, seed=cp)
    frozen_cli.create(args) # atomic copy and reset counters, does NOT move parent model
    exp=EXPERIMENTS/name
    state={
        'kind':OWN_MARK,'experiment':name,'created_utc':now(),
        'original_seed_read_only':str(cp),'original_baseline':baseline,
        'completed_rounds':0,'history':[],'status':'created',
        'rotation_student_steps':ROTATION,'round_steps':STEP_BLOCK,
        'last_checkpoint_step':0,'opponents':list(TEACHERS),
        'note':'Experimental 1v1 PPO against frozen native teacher actors; no auto promotion.'
    }
    atomic_json(state_path,state)
    return state


def verify_journal(name=CHALLENGER):
    exp=EXPERIMENTS/name
    file=_state_path(exp)
    if not file.is_file(): raise FileNotFoundError('Challenger not initialized: '+str(file))
    state=json.loads(file.read_text(encoding='utf-8'))
    if state.get('kind')!=OWN_MARK or state.get('experiment')!=name or state.get('opponents')!=list(TEACHERS):
        raise RuntimeError('Experiment is not our protected tri-teacher branch')
    cp=latest(exp)
    if state['last_checkpoint_step']>int(cp.name):
        raise RuntimeError('Journal is ahead of saved checkpoint; investigate before resuming')
    return exp, state, cp


def audit_teachers(output):
    """Require all 3 teachers actually appear in CPP PPO logs."""
    active=re.findall(r'\[FrozenNexto\] PPO cycle=\d+ teacher=(nexto|cycle9|wavedash)\b',output)
    counts={k:active.count(k) for k in TEACHERS}
    return counts


def evaluate_report_text(exp,first_bytes=0):
    file=exp/'reports'/'frozen_ppo.log'
    if not file.is_file():return ''
    with file.open('rb') as f:
        f.seek(first_bytes)
        return f.read().decode('utf-8',errors='replace')


def _process_round(exp, state, rotation, games, save_every, round_ix, seed):
    start_cp=latest(exp)
    start=int(start_cp.name)
    logfile=exp/'reports'/'frozen_ppo.log'
    existing_size=logfile.stat().st_size if logfile.is_file() else 0
    cmd=[sys.executable, str(HERE/'frozen_cli.py'), 'run', '--name', exp.name,
         '--steps',str(rotation*3),'--rotation',str(rotation),'--games',str(games),
         '--save-every',str(save_every),'--run-seed',str(seed)]
    pathlog=exp/'reports'/'extended_rotation.log'
    pathlog.parent.mkdir(parents=True,exist_ok=True)
    print(f'\n=== ROUND {round_ix} / starting checkpoint {start} ===',flush=True)
    print(f'Nexto -> Cycle 9 -> Wavedash; {rotation} student steps each; expect at least {rotation*3} new steps',flush=True)
    t0=time.monotonic()
    with pathlog.open('a',encoding='utf-8') as f:
        f.write(f'\n[{now()}] START round={round_ix} checkpoint={start} cmd={cmd!r}\n'); f.flush()
        with subprocess.Popen(cmd,cwd=str(HERE),env=os.environ.copy(),
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace') as proc:
            for line in proc.stdout:
                f.write(line); f.flush()
                if any(tag in line for tag in ('[FrozenNexto] PPO cycle=', 'saved student checkpoint', 'ERROR:', 'SUCCESS:', 'target student steps')):
                    print(line.rstrip(),flush=True)
            rc=proc.wait()
        f.write(f'[{now()}] EXIT rc={rc} elapsed={time.monotonic()-t0:.2f}s\n')
    cp=latest(exp)
    new_step=int(cp.name)
    segment=evaluate_report_text(exp,existing_size)
    counts=audit_teachers(segment)
    fatal=any(x in segment for x in ('RG FATAL ERROR:', 'Exception thrown during main learner loop:', 'ERROR: Trainer reported a fatal error'))
    # A deliberate Research Hub safe-stop causes frozen_cli.run to return 1
    # because the total requested steps were not reached. Distinguish from failure.
    safely_paused=('[Research Hub] Safe stop requested' in segment
                   and '[Research Hub] Checkpoint saved; stopping.' in segment
                   and new_step>start and not fatal)
    target_reached=(new_step>=start+rotation*3)
    good=(rc==0 and target_reached and not fatal and all(n>0 for n in counts.values()))
    return {'started_utc':now(),'round':round_ix,'old_checkpoint':start,'new_checkpoint':new_step,
            'teachers_ppo_iterations':counts,'elapsed_seconds':round(time.monotonic()-t0,2),
            'return_code':rc,'fatal':fatal,'success':good,'paused':safely_paused,
            'full_requested_steps_saved':target_reached}


def training(name=CHALLENGER, *, rounds=5, games=4, rotation=ROTATION, save_every=32768,
             seed=734891, baseline=BASELINE, seed_checkpoint=None):
    if not (1<=rounds<=100 and 1<=games<=16 and 1<=seed<=2_000_000_000):
        raise ValueError('Invalid rounds/games/seed')
    if rotation!=ROTATION:
        raise ValueError('Use 65536 student steps per teacher for a reproducible three-opponent cycle')
    if save_every<8192 or save_every>262144 or save_every%4096:
        raise ValueError('Save interval must be a multiple of 4096 in [8192, 262144]')
    teachers=validate_setup()
    print('Frozen teacher checkpoints:')
    for n,p in teachers.items():print(f'  {n}: {p}')
    # Initialize only after verifying prerequisites. Existing branch is always reused.
    state=init_challenger(name,baseline,seed=seed_checkpoint)
    exp=EXPERIMENTS/name
    lock=exp/'extended_rotation.lock'
    try:
        with lock.open('x',encoding='utf-8') as f:
            f.write(json.dumps({'pid':os.getpid(),'utc':now()}))
    except FileExistsError:
        raise RuntimeError(f'{lock} already exists. Do not start duplicate trainers. Check PIDs before removing stale locks.')
    try:
        exp,state,cp=verify_journal(name)
        # Don't allow overlapping hub training regardless of whether it is alive.
        if (exp/'launch.lock').exists():
            raise RuntimeError('Research Hub launch.lock exists: trainer already active or lock needs inspection')
        # Strict mismatch checks on resumes.
        if 'training_config' in state:
            conf=state['training_config']
            if (conf['games'],conf['rotation'],conf['save_every'])!=(games,rotation,save_every):
                raise RuntimeError('Cannot silently change game count, rotation or save interval on existing branch')
        else:
            state['training_config']={'games':games,'rotation':rotation,'save_every':save_every,'seed_base':seed}
            atomic_json(_state_path(exp),state)
        # No double-running after a stop requested while a process was already gone.
        if (exp/'request_safe_stop.flag').exists():
            raise RuntimeError('request_safe_stop.flag still exists. Check whether a training process is running before retrying.')
        if rounds<=state['completed_rounds']:
            print(f'Completed {state["completed_rounds"]} rounds. Nothing more requested; select a larger preset.')
            return
        print(f'\nCHALLENGER: {exp}')
        print(f'Checkpoint: {latest(exp)}')
        print(f'Target total rounds: {rounds} (done: {state["completed_rounds"]}); no auto-promotion')
        print('Safe stop: run STOP_AFTER_PPO.bat from another window.')
        state['status']='running';state['last_started_utc']=now()
        atomic_json(_state_path(exp),state)
        for round_ix in range(state['completed_rounds']+1,rounds+1):
            # Change seed per round to increase state coverage; fix saved model stat ordering.
            round_seed=(seed+round_ix*104729) % 1_999_999_999 + 1
            result=_process_round(exp,state,rotation,games,save_every,round_ix,round_seed)
            print('Round report:',json.dumps(result,indent=2),flush=True)
            state['history'].append(result)
            state['last_checkpoint_step']=result['new_checkpoint']
            if result['success']:
                state['completed_rounds']+=1
                state['status']='checkpointed'; state['last_updated_utc']=now()
                atomic_json(_state_path(exp),state)
            elif result['paused']:
                state['status']='paused'; state['last_updated_utc']=now()
                atomic_json(_state_path(exp),state)
                print('SAFE PAUSE confirmed. Restart the same launcher later to resume.',flush=True)
                return
            else:
                state['status']='error'; state['last_updated_utc']=now()
                atomic_json(_state_path(exp),state)
                raise RuntimeError('Round did not complete successfully; original checkpoints preserved. '
                                   'Check frozen_ppo.log and extended_rotation.log. No automatic resume.')
        state['status']='finished'; state['last_updated_utc']=now()
        atomic_json(_state_path(exp),state)
        print('\nALL REQUESTED ROUNDS FINISHED. Latest checkpoint:',latest(exp),flush=True)
        print('DO NOT promote automatically: benchmark in RocketSim vs the three teachers and inspect gameplay.',flush=True)
    finally:
        lock.unlink(missing_ok=True)


def status(name=CHALLENGER):
    exp,state,cp=verify_journal(name)
    print('Experiment:',exp)
    print('Status:',state['status'])
    print('Completed rounds:',state['completed_rounds'])
    print('Latest checkpoint:',cp)
    for r in state['history'][-6:]:
        print(f'  Round {r["round"]}: {r["old_checkpoint"]} -> {r["new_checkpoint"]} '
              f'Nexto/Cycle9/Wavedash={list(r["teachers_ppo_iterations"].values())} '
              f'{r["elapsed_seconds"]}sec {"PASS" if r["success"] else "PAUSED" if r["paused"] else "FAIL"}')
    print('No automatic promotion. Original Cycle9 and Wavedash remain unchanged.')


def stop(name=CHALLENGER):
    exp,state,cp=verify_journal(name)
    if not (exp/'extended_rotation.lock').exists():
        print('No active extended_rotation.lock; nothing to stop.');return
    stop_flag=exp/'request_safe_stop.flag'
    if stop_flag.exists():print('Safe stop already requested.');return
    stop_flag.write_text('Stop at next PPO boundary; save checkpoint.\n',encoding='utf-8')
    print('SAFE STOP REQUESTED. Trainer will save at next PPO boundary:',stop_flag)


def main(argv=None):
    p=argparse.ArgumentParser(description='Safe extended tri-teacher PPO: Nexto/Cycle9/Wavedash')
    subs=p.add_subparsers(dest='command',required=True)
    q=subs.add_parser('start');q.add_argument('--rounds',type=int,default=5)
    q.add_argument('--name',default=CHALLENGER);q.add_argument('--baseline',default=BASELINE)
    q.add_argument('--seed-checkpoint',default=None)
    q.add_argument('--games',type=int,default=4)
    q.add_argument('--rotation',type=int,default=ROTATION)
    q.add_argument('--save-every',type=int,default=32768)
    q.add_argument('--seed',type=int,default=734891)
    for op in ('status','stop'):
        q=subs.add_parser(op);q.add_argument('--name',default=CHALLENGER)
    args=p.parse_args(argv)
    if args.command=='start':training(args.name,rounds=args.rounds,games=args.games,rotation=args.rotation,
                            save_every=args.save_every,seed=args.seed,baseline=args.baseline,
                            seed_checkpoint=args.seed_checkpoint)
    elif args.command=='status':status(args.name)
    elif args.command=='stop':stop(args.name)


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('ERROR:',e,file=sys.stderr)
        raise SystemExit(1)
