"""AFK Improved — isolated aggressive policy research for native Nexto checkpoints.

Runs independent, larger-step PPO attempts, then compares their saved candidates
against original Nexto AND the untouched Cycle 9 checkpoint using a common seed.
No copies to main champion or AFK Improved's best_verified; no automatic promotion.
Native AutoLeague/RocketSim support remains 1v1 only. CPU-only for the bundled JIT.
"""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
SOURCE_SHA = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
BASE = ROOT/'data'/'afk_improved'/'aggressive_research'
PAUSE = BASE/'pause.request'
STATE = BASE/'research_state.json'
SUMMARY = BASE/'research_evaluations.json'

# Intentionally explore substantial policy changes. All variants stay isolated.
VARIANTS = (
    ('control',    3e-6,  .60, .10, .001),
    ('explore',    1.2e-5,.25, .18, .002),
    ('aggressive', 3e-5,  .12, .22, .003),
    ('radical',    8e-5,  .08, .25, .005),
)

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def read_json(p, default=None):
    try:return json.loads(Path(p).read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):return default

def atomic_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_name(p.name+'.partial')
    try:t.write_text(json.dumps(obj,indent=2,sort_keys=True),encoding='utf-8');os.replace(t,p)
    finally:t.unlink(missing_ok=True)

def lock_byte(file, message):
    """An OS-level nonblocking lock; stale empty lockfiles do not block runs."""
    file=Path(file)
    with file.open('a+b') as f:
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise RuntimeError(message) from e
            try:yield
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:raise RuntimeError(message) from e
            try:yield
            finally:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
lock_byte=contextlib.contextmanager(lock_byte)

def preflight(root=ROOT, *, idle=True):
    src=root/'data'/'autoleague'/'backups'/SOURCE.name
    if not src.is_file():raise FileNotFoundError(f'Cycle 9 missing: {src}')
    if sha(src)!=SOURCE_SHA:raise RuntimeError('Protected Cycle 9 hash mismatch; refusing training')
    for f in ('auto_league.py','native_nexto.py','nexto_teacher.py'):
        if not (root/f).exists():raise FileNotFoundError(root/f)
    if idle:
        for path,label in [
            (root/'data'/'autoleague'/'.training.lock','Main AutoLeague'),
            (root/'data'/'afk_improved'/'.runner.lock','AFK Improved PPO'),
            (root/'data'/'afk_improved'/'learning'/'.learning.lock','Replay/TAS learner')
        ]:
            if path.is_file():
                with lock_byte(path,f'{label} is still running. Wait for completion before research.'):pass
    return src

def variant_dir(name):return BASE/'branches'/name

def branch_candidate(name):
    folder=variant_dir(name)
    # `--no-promote` archives the completed experimental candidate here.
    candidates=sorted((folder/'inconclusive').glob('*.pt')) if (folder/'inconclusive').exists() else []
    if len(candidates)!=1:
        raise RuntimeError(f'Expected one archived experimental candidate in {folder}, found {len(candidates)}. No guess.')
    return candidates[0]

def optional_prior_candidate():
    """Prior AFK cycle-9 candidate (67.5% on its earlier 40-game screen), if unambiguous."""
    folder=ROOT/'data'/'afk_improved'/'league'/'inconclusive'
    matches=sorted(folder.glob('*_cycle0009.pt')) if folder.exists() else []
    if len(matches)>1:raise RuntimeError('Ambiguous AFK cycle-9 candidates; inspect manually')
    return matches[0] if matches else None

def report_file(name):
    files=sorted((variant_dir(name)/'reports').glob('*.json'))
    if len(files)!=1:raise RuntimeError(f'Expected one training evaluation for {name}, found {len(files)}')
    return files[0]

def execute_branch(name, lr, anchor, clip, entropy, *, steps, seed, training_games):
    output=variant_dir(name)
    state=read_json(output/'league_state.json',{})
    if int(state.get('cycle',1))>1:
        cand=branch_candidate(name)
        print(f'[SKIP] {name} already trained: {cand.name}',flush=True)
        return cand
    output.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(ROOT/'auto_league.py'),
         '--source',str(SOURCE),'--data-dir',str(output),'--device','cpu',
         '--no-promote','--no-replays','--max-cycles','1',
         '--segment-decisions',str(steps),'--actor-lr',str(lr),
         '--anchor',str(anchor),'--clip',str(clip),'--entropy',str(entropy),
         '--seed',str(seed),'--eval-games',str(training_games)]
    print(f'[TRAIN] {name}: lr={lr:g}, anchor={anchor}, clip={clip}, entropy={entropy}',flush=True)
    # Robust log flushing; last valid PPO rollout checkpoint is saved by AutoLeague.
    log=output/'training.log'
    with log.open('a',encoding='utf-8') as f:
        f.write(f'\n=== {utc()} CMD: {cmd!r} ===\n');f.flush()
        with subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,encoding='utf-8',errors='replace',bufsize=1) as proc:
            for line in proc.stdout:
                sys.stdout.write(line);f.write(line);f.flush()
            rc=proc.wait()
    if rc!=0:raise RuntimeError(f'{name} returned {rc}; read {log}. Resume with same launcher.')
    return branch_candidate(name)

def decide_score(report):
    test=report['candidate_vs_nexto'];base=report['champion_vs_nexto'];head=report['candidate_vs_champion']
    c,b,h=(v['score'] for v in (test,base,head))
    # Research-only labels. The final acceptance decision must use a longer, new benchmark.
    diverse=min(v['unique_starts'] for v in (test,base,head)) >= max(4,report['games']//3)
    status='promising_for_longer_test' if diverse and c>=b+0.025 and h>=0.50 else 'unproven_or_regressed'
    return {'status':status,'score_vs_nexto':c,'cycle09_vs_nexto':b,
            'score_vs_cycle09':h,'scenario_diversity_ok':diverse,
            'wins_vs_nexto':test['outcomes'].get('ours',0),'losses_vs_nexto':test['outcomes'].get('nexto',0),
            'draws_vs_nexto':test['outcomes'].get('draw',0)}

def evaluate(variant_names, *, games, seed):
    # Load actual saved policy states and replay identical holdout conditions.
    import auto_league as league
    from nexto_teacher import NextoTeacher
    baseline=league.actor_from(SOURCE,'cpu')
    teacher=NextoTeacher('cpu')
    existing=read_json(SUMMARY,{}) or {}
    if existing.get('seed')!=seed or existing.get('games')!=games or existing.get('source_sha')!=SOURCE_SHA:
        existing={'created_utc':utc(),'seed':seed,'games':games,'source_sha':SOURCE_SHA,
                  'evaluation_note':'1v1 first-goal episodes; held-out after training. Do not auto-promote.',
                  'branches':{}}
    for name in variant_names:
        if PAUSE.exists():print('[PAUSE] Safe pause before next evaluation');break
        ckpt=optional_prior_candidate() if name=='previous_afk_cycle09' else branch_candidate(name)
        if ckpt is None:print('[SKIP] Previous AFK cycle 9 candidate not found');continue
        digest=sha(ckpt)
        cached=existing['branches'].get(name)
        if cached and cached.get('sha256')==digest:
            print(f'[SKIP] Previously evaluated {name} SHA {digest[:12]}');continue
        print(f'[EVAL] {name} vs Cycle 9 and Nexto, {games} paired episodes each',flush=True)
        actor=league.actor_from(ckpt,'cpu')
        result=league.run_gate(actor,baseline,teacher.actor,teacher,games=games,
                               decisions=750,seed=seed)
        verdict=decide_score(result)
        output=BASE/'reports'/f'{name}_{digest[:16]}_vs_cycle09.json'
        league.atomic_json(output,result)
        existing['branches'][name]={'sha256':digest,'checkpoint':str(ckpt.relative_to(ROOT)),
                                   'report':str(output.relative_to(ROOT)),**verdict}
        atomic_json(SUMMARY,existing)
        print(f'[{name}] {verdict}',flush=True)
    return existing

def run(args):
    BASE.mkdir(parents=True,exist_ok=True)
    with lock_byte(BASE/'.research.lock','Aggressive Research is already running'):
        source=preflight()
        if shutil.disk_usage(BASE).free < 2*1024**3:raise RuntimeError('Less than 2 GB free; refusing research')
        source_sha=sha(source)
        variants=VARIANTS if args.radical else VARIANTS[:-1]
        names=[v[0] for v in variants]
        if args.command in ('run','train'):
            if args.command=='run' and PAUSE.exists():
                raise RuntimeError('Research is paused; use --resume after you are ready')
            for i,(name,lr,anchor,clip,entropy) in enumerate(variants):
                if PAUSE.exists():print('[PAUSE] No new training branch started');break
                atomic_json(STATE,{'status':'training','current_branch':name,'source_sha':SOURCE_SHA,
                                   'updated_utc':utc()})
                try:execute_branch(name,lr,anchor,clip,entropy,steps=args.steps,
                                   seed=args.seed + i*100019,training_games=args.train_eval_games)
                except Exception as e:
                    # One aggressive branch may diverge; quarantine its logs and continue.
                    print(f'[FAIL] {name}: {type(e).__name__}: {e}',file=sys.stderr,flush=True)
                    atomic_json(variant_dir(name)/'research_error.json',{'error':str(e),'utc':utc()})
        if args.command in ('run','evaluate') and not PAUSE.exists():
            completed=[n for n in names if read_json(variant_dir(n)/'league_state.json',{}).get('cycle',1)>1]
            if optional_prior_candidate() is not None:completed.append('previous_afk_cycle09')
            if completed:evaluate(completed,games=args.eval_games,seed=args.holdout_seed)
        if sha(source)!=source_sha:raise RuntimeError('Source Cycle 9 unexpectedly changed! Stop and investigate')
        atomic_json(STATE,{'status':'paused' if PAUSE.exists() else 'finished',
                           'source_sha':source_sha,'updated_utc':utc(),
                           'note':'No automatic promotion. Existing production model untouched.'})

def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['check','run','train','evaluate','pause','resume','status'])
    p.add_argument('--radical',action='store_true',help='Enable isolated 8e-5 learning-rate variant')
    p.add_argument('--steps',type=int,default=8192)
    p.add_argument('--train-eval-games',type=int,default=40)
    p.add_argument('--eval-games',type=int,default=120)
    p.add_argument('--seed',type=int,default=610233)
    p.add_argument('--holdout-seed',type=int,default=100993311)
    a=p.parse_args(argv)
    if a.command=='pause':
        BASE.mkdir(parents=True,exist_ok=True);PAUSE.write_text('pause after current branch\n');
        print('Pause requested. Current AutoLeague cycle ends first.');return 0
    if a.command=='status':
        print(json.dumps({'state':read_json(STATE,{}),'summary':read_json(SUMMARY,{})},indent=2));return 0
    if a.command=='resume':PAUSE.unlink(missing_ok=True);a.command='run'
    if a.command=='check':
        print('Cycle 9 SHA256:',sha(preflight()))
        print('Variants:',[(name,lr) for name,lr,*_ in VARIANTS]);
        print('No data or model weights modified. No RocketSim used in check.');return 0
    if a.steps<512 or a.steps>131072 or a.train_eval_games<20 or a.eval_games<40:
        p.error('Invalid settings; steps 512..131072, training eval >=20, holdout eval >=40')
    run(a);return 0
if __name__=='__main__':
    try:sys.exit(cli())
    except Exception as e:print(f'ERROR: {type(e).__name__}: {e}',file=sys.stderr);sys.exit(1)
