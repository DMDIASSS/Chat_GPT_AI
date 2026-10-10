"""AFK Improved v1: isolated, resumable long-running AutoLeague orchestrator.

This does not touch main AutoLeague. A secondary independently-gated best is kept.
Stopping uses data/afk_improved/pause.request; finishes a full training/evaluation
cycle before exiting. No promises of monotonically increasing or unbounded skill.
"""
from __future__ import annotations
import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime

import afk_improved_core as core
from afk_device_safety import choose_device, check_cpu_policy


def say(msg):
    line=f'[{datetime.now().strftime("%H:%M:%S")}] {msg}'
    print(line,flush=True)
    core.DATA.mkdir(parents=True,exist_ok=True)
    with (core.DATA/'runner.log').open('a',encoding='utf-8') as fh:fh.write(line+'\n')


@contextlib.contextmanager
def process_lock():
    core.DATA.mkdir(parents=True,exist_ok=True)
    with core.LOCK.open('a+b') as fh:
        fh.seek(0);fh.write(b'0');fh.flush();fh.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as ex:raise RuntimeError('AFK Improved is already running') from ex
        else:
            import fcntl
            try:fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as ex:raise RuntimeError('AFK Improved is already running') from ex
        try:yield
        finally:
            if os.name=='nt':
                fh.seek(0);msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(fh.fileno(),fcntl.LOCK_UN)


def status(**kwargs):
    prior=core.read_json(core.STATUS,{}) or {}
    prior.update(kwargs);prior['updated_utc']=core.now()
    core.atomic_json(core.STATUS,prior)


def validate(args):
    if args.cycles<0 or args.hours<0 or args.eval_games<20 or args.segment_decisions<96 or args.rollout<32:
        raise ValueError('Bad settings: cycles>=0 eval_games>=20 segment_decisions>=96 rollout>=32')
    core.assert_main_league_idle()
    hashes=core.verify_starting_files()
    if core.BEST.exists() or core.BEST_STATE.exists():
        if not core.existing_checkpoint_verified():
            raise RuntimeError('Verified best checksum mismatch, refusing to run')
    # For an existing run, source must not be overwritten or reinitialized.
    lp=core.LEAGUE/'league_state.json'; cp=core.LEAGUE/'champion.pt'
    if lp.exists() != cp.exists():raise RuntimeError('Partial experiment league detected; fix manually')
    if lp.exists():
        state=core.read_json(lp,{})
        if state.get('champion_sha')!=core.hash_file(cp) and state.get('phase')!='promoting':
            raise RuntimeError('Experiment champion SHA mismatch')
    return hashes


def independent_verification(cycle, eval_games):
    import auto_league as league
    from nexto_teacher import NextoTeacher
    previous=league.actor_from(core.BEST,'cpu')
    new=league.actor_from(core.LEAGUE/'champion.pt','cpu')
    teacher=NextoTeacher('cpu')
    report=league.run_gate(new,previous,teacher.actor,teacher,games=eval_games,
        decisions=750,seed=1919197+cycle*209759)
    report['experiment_cycle']=cycle
    report['new_sha256']=core.hash_file(core.LEAGUE/'champion.pt')
    report['previous_sha256']=core.hash_file(core.BEST)
    # Gate conservative by design, no unverified automatic replacement.
    passed=report['verdict']=='PROMOTE' and min(
        report[k]['unique_starts'] for k in ('candidate_vs_nexto','champion_vs_nexto','candidate_vs_champion'))>=eval_games//3
    report['accepted_best']=bool(passed)
    output=core.DATA/'reports'/f'verify_cycle{cycle:04d}.json'
    core.atomic_json(output,report)
    if passed:
        old=core.DATA/'verified_history'/f'{report["previous_sha256"][:14]}.pt'
        if not old.exists(): core.atomic_copy(core.BEST,old)
        core.atomic_copy(core.LEAGUE/'champion.pt',core.BEST)
        core.atomic_json(core.BEST_STATE,{'sha256':core.hash_file(core.BEST),'verified_cycle':cycle,
                                         'created_utc':core.now(),'origin':str(core.LEAGUE/'champion.pt'),
                                         'last_report':str(output.relative_to(core.ROOT)),
                                         'status':'passed_independent_gate'})
        say('NEW independently verified best saved in experiment only')
    else:say('Experimental promotion not independently accepted; verified best unchanged')
    return report


def run(args):
    with process_lock():
        hashes=validate(args)
        # Crucial safety check: the bundled Nexto JIT model contains a baked-in
        # CPU action lookup, which throws cpu-vs-cuda matmul errors under CUDA.
        from native_nexto import SOURCE_MODEL
        safe_device, device_note = choose_device(args.device, SOURCE_MODEL)
        args.device = safe_device
        say('DEVICE CHECK: ' + device_note)
        core.init_best()
        core.STOP_REQUEST.unlink(missing_ok=True)
        total=0
        status(phase='running',started_utc=core.now(),best_sha=core.hash_file(core.BEST),cycles_this_session=0,device=args.device,device_note=device_note)
        say('AFK Improved: isolated Cycle 9 lineage, safety hashes recorded.')
        say('SELF-PLAY/Nexto 1v1 only. Replay files are NOT fed to the policy.')
        deadline=time.monotonic()+args.hours*3600 if args.hours else None
        previous_sha=core.hash_file(core.LEAGUE/'champion.pt') if (core.LEAGUE/'champion.pt').exists() else core.CYCLE9_SHA
        try:
            while args.cycles==0 or total<args.cycles:
                if core.STOP_REQUEST.exists():
                    say('Safe pause requested before next cycle');break
                if deadline and time.monotonic()>=deadline:
                    say('Time budget reached at safe cycle boundary');break
                free_bytes=shutil.disk_usage(core.DATA).free
                if free_bytes < int(args.min_free_gb*1024**3):
                    say(f'Insufficient disk free: {free_bytes/1024**3:.2f} GB; pausing before next cycle')
                    status(phase='low_disk',free_gb=round(free_bytes/1024**3,2));break
                cmd=[sys.executable,str(core.ROOT/'auto_league.py'),
                     '--source',str(core.CYCLE9),'--data-dir',str(core.LEAGUE),
                     '--max-cycles','1','--no-replays',
                     '--segment-decisions',str(args.segment_decisions),'--rollout',str(args.rollout),
                     '--eval-games',str(args.eval_games),'--eval-decisions','750',
                     '--backup-minutes','5','--device',args.device]
                status(phase='training',cycles_this_session=total)
                say('Starting/resuming one full AutoLeague cycle. Safe pause occurs AFTER it completes.')
                # stdout streamed into runner log so the user can see live PPO progress.
                with subprocess.Popen(cmd,cwd=core.ROOT,stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1) as proc:
                    for line in proc.stdout:
                        sys.stdout.write(line);sys.stdout.flush()
                        with (core.DATA/'runner.log').open('a',encoding='utf-8') as fh:fh.write(line)
                    exitcode=proc.wait()
                if exitcode!=0:raise RuntimeError(f'AutoLeague returned {exitcode}; see runner.log')
                total+=1
                state=core.read_json(core.LEAGUE/'league_state.json',{})
                cycle=int(state.get('cycle',1))-1
                current_sha=core.hash_file(core.LEAGUE/'champion.pt')
                status(cycles_this_session=total,completed_cycle=cycle,experimental_sha=current_sha,
                       best_sha=core.hash_file(core.BEST))
                if current_sha!=previous_sha and current_sha!=core.hash_file(core.BEST):
                    say(f'Experimental champion changed at cycle {cycle}; validating against verified best')
                    status(phase='verifying')
                    independent_verification(cycle,max(args.eval_games,80))
                    status(best_sha=core.hash_file(core.BEST))
                previous_sha=current_sha
                core.verify_untouched(hashes)
                if core.STOP_REQUEST.exists():break
            status(phase='paused' if core.STOP_REQUEST.exists() else 'finished',
                   cycles_this_session=total,best_sha=core.hash_file(core.BEST))
            say('Stopped at safe cycle boundary. Original champion/state unchanged.')
        except Exception as ex:
            status(phase='error',error=f'{type(ex).__name__}: {ex}')
            say(f'ERROR: {type(ex).__name__}: {ex}');raise
        finally:
            core.verify_untouched(hashes)
            core.STOP_REQUEST.unlink(missing_ok=True)


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cycles',type=int,default=0,help='0=until paused')
    p.add_argument('--hours',type=float,default=0,help='0=until paused; stop before next cycle after budget')
    p.add_argument('--min-free-gb',type=float,default=2.0)
    p.add_argument('--segment-decisions',type=int,default=8192)
    p.add_argument('--rollout',type=int,default=512)
    p.add_argument('--eval-games',type=int,default=40)
    p.add_argument('--device',choices=['cpu','cuda:0'],default='cpu')
    p.add_argument('--check',action='store_true')
    p.add_argument('--pause',action='store_true')
    args=p.parse_args(argv)
    if args.pause:
        core.DATA.mkdir(parents=True,exist_ok=True)
        core.STOP_REQUEST.write_text('stop after cycle\n',encoding='utf8')
        print('Pause requested; wait for current PPO cycle/evaluation to finish.')
        return 0
    if args.check:
        h=validate(args)
        print('Starting model verified:',core.CYCLE9_SHA[:16]);print('Protected hashes:',len(h));
        from native_nexto import SOURCE_MODEL
        safe_device, note=choose_device(args.device,SOURCE_MODEL)
        print('Device result:',safe_device, note)
        print(check_cpu_policy(SOURCE_MODEL))
        print('Source present; real RocketSim preflight not run.');return 0
    run(args)
    return 0
if __name__=='__main__':sys.exit(cli())
