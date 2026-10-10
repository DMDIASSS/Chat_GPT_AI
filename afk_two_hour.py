"""AFK native Nexto experiment: evaluate finalists, train in an isolated AutoLeague,
then independently benchmark the resulting policies. Nothing promotes into the
user's existing data/autoleague league. Designed for the Chat_GPT_AI project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import torch

import auto_league as league
from nexto_teacher import NextoTeacher

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / 'data' / 'autoleague'
RUNS = ROOT / 'data' / 'afk_runs'
# Exact checkpoint hashes from the completed tournament, to detect wrong files.
EXPECTED_CYCLE09 = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
EXPECTED_WAVEDASH = '57e330a7b4d3487fd304ec9e3252b847df3fea1e59c6351fc7cd4548156809b3'


class PauseRequested(Exception):
    """Requested pause after the last durable PPO checkpoint (or stage boundary)."""


class TimeBudgetReached(Exception):
    """Normal end of the training budget at a completed checkpoint boundary."""


class Logger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
    def __call__(self, message):
        line = f'[{datetime.now().strftime("%H:%M:%S")}] {message}'
        print(line, flush=True)
        with self.path.open('a', encoding='utf-8') as out:
            out.write(line + '\n')


def utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    league.atomic_json(path, data)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def file_hash(path):
    return league.sha256(path)


def require_league_state():
    champion = MAIN / 'champion.pt'
    statepath = MAIN / 'league_state.json'
    if not (champion.is_file() and statepath.is_file()):
        raise FileNotFoundError('Expected data/autoleague/champion.pt and league_state.json')
    state = read_json(statepath)
    if state.get('phase') != 'train':
        raise RuntimeError('Main league is mid-promotion; STOP and resolve before AFK run')
    digest = file_hash(champion)
    if digest != state.get('champion_sha'):
        raise RuntimeError('Main champion SHA does not match league_state.json: refusing to continue')
    return champion, statepath, state


def source_paths():
    return {
        'champion': MAIN / 'champion.pt',
        'cycle09': ROOT / 'data' / 'autoleague' / 'backups' /
          '20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt',
        'wavedash': ROOT / 'data' / 'mechanics' / 'wavedash' / 'last.pt',
    }


def choose_inputs(log):
    champion, statepath, state = require_league_state()
    sources = source_paths()
    if not sources['cycle09'].is_file():
        raise FileNotFoundError('Missing the cycle 9 checkpoint: ' + str(sources['cycle09']))
    if file_hash(sources['cycle09']) != EXPECTED_CYCLE09:
        raise RuntimeError('Cycle 9 checkpoint differs from the tournament result; stop and inspect')
    if sources['wavedash'].is_file():
        if file_hash(sources['wavedash']) != EXPECTED_WAVEDASH:
            raise RuntimeError('Wavedash checkpoint changed since the tournament; stop and inspect')
    else:
        log('Wavedash not found: continuing with champion and cycle09 only')
        sources.pop('wavedash')
    for name, path in sources.items():
        # This verifies actual actor weights and architecture, not just extension.
        league.actor_from(path, 'cpu')
        log(f'OK {name}: {path.relative_to(ROOT)} SHA={file_hash(path)[:16]}')
    check = {str(p): file_hash(p) for p in (champion, statepath)}
    if (MAIN / 'candidate.pt').exists():
        check[str(MAIN / 'candidate.pt')] = file_hash(MAIN / 'candidate.pt')
    return sources, check, state


def keep_inputs(sources, run_dir):
    folder = run_dir / 'inputs'
    folder.mkdir(parents=True, exist_ok=False)
    out = {}
    for name, origin in sources.items():
        dest = folder / f'{name}.pt'
        league.atomic_copy(origin, dest)
        if file_hash(dest) != file_hash(origin):
            raise RuntimeError('Backup copy SHA mismatch for ' + name)
        out[name] = dest
    return out


def paired_cases(seed, pairs):
    """Same random scenario and seed on blue and orange; independent seeds per round."""
    rng = random.Random(seed)
    cases = []
    for i in range(pairs):
        s = rng.randrange(1, 2**31)
        kind = 'kickoff' if i % 4 == 0 else 'grounded'
        cases.extend([(s, False, kind), (s, True, kind)])
    return cases


def wld(result):
    out = result['outcomes']
    return f'W={out.get("ours",0)} L={out.get("nexto",0)} D={out.get("draw",0)}'


def try_eval(actor_path, enemy, teacher, engine, cases, decisions, title, log):
    # Only snapshots located in the new AFK run can be tested while training runs.
    actor = league.actor_from(actor_path, 'cpu')
    r = league.duel(actor, enemy, teacher, engine, cases, decisions, label=title)
    log(f'{title}: {wld(r)} | score={r["score"]:.3f} | starts={r["unique_starts"]}/{r["episodes"]}')
    return r


def evaluate_pre(inputs, args, log):
    from rlgym.rocket_league.sim import RocketSimEngine
    teacher = NextoTeacher('cpu')
    nexto = teacher.actor
    engine = RocketSimEngine(rlbot_delay=False)
    nexto_scores = {}
    head_to_head = []
    start = time.monotonic()
    episodes = 0
    try:
        tests = paired_cases(args.seed + 100001, args.pre_pairs)
        for name, path in inputs.items():
            r = try_eval(path, nexto, teacher, engine, tests, args.decisions, f'PRE {name} vs Nexto', log)
            nexto_scores[name] = r
            episodes += len(tests)
        names = list(inputs)
        cases = paired_cases(args.seed + 200003, args.pre_h2h_pairs)
        actors = {n: league.actor_from(inputs[n], 'cpu') for n in names}
        for i, a in enumerate(names):
            for b in names[i+1:]:
                r = league.duel(actors[a], actors[b], teacher, engine, cases, args.decisions,
                                label=f'PRE {a} vs {b}')
                head_to_head.append({'a': a, 'b': b, 'result': r})
                log(f'PRE {a} vs {b}: {wld(r)} score(A)={r["score"]:.3f}')
                episodes += len(cases)
        control_cases = paired_cases(args.seed + 300007, max(8,args.pre_h2h_pairs//2))
        control = league.duel(nexto, nexto, teacher, engine, control_cases, args.decisions,
                              label='CONTROL original Nexto vs itself')
        episodes += len(control_cases)
    finally:
        engine.close()
    # The score vs Nexto has the highest weight because that is the explicit goal.
    pair_scores = {n: [] for n in names}
    for row in head_to_head:
        s = row['result']['score']
        pair_scores[row['a']].append(s)
        pair_scores[row['b']].append(1 - s)
    ranks = sorted(names, key=lambda n: (0.8*nexto_scores[n]['score'] +
        0.2*(sum(pair_scores[n])/max(1,len(pair_scores[n]))),
        nexto_scores[n]['score']), reverse=True)
    selected = ranks[0]
    report = {
        'kind': 'afk_preliminary_independent_first_goal', 'created_utc': utc(),
        'pairs_vs_nexto': args.pre_pairs, 'pairs_h2h': args.pre_h2h_pairs,
        'seed': args.seed, 'scenario_protocol': 'paired blue/orange, kickoff+grounded, greedy policies',
        'nexto_scores': nexto_scores, 'head_to_head': head_to_head,
        'nexto_vs_itself_control': control,
        'selection_scores': {n: 0.8*nexto_scores[n]['score'] + 0.2*(sum(pair_scores[n])/max(1,len(pair_scores[n]))) for n in names},
        'ranking': ranks, 'selected_for_isolated_training': selected,
        'elapsed_seconds': time.monotonic()-start,
        'episodes': episodes,
        'warning': 'First-goal episodes, not five-minute matches; selection is noisy, especially for short runs.',
    }
    log(f'PRE winner selected for isolated training: {selected}; score vs Nexto {nexto_scores[selected]["score"]:.3f}')
    return report


def training_isolated(base, league_dir, args, deadline, log, run_dir):
    """Run original AutoLeague until the deadline, interrupting ONLY after a saved rollout.

    Existing AutoLeague backs up its isolated champion+candidate and uses an
    internal gate. Automatic promotions are confined to this new league_dir.
    """
    if time.monotonic() >= deadline:
        log('Skipping training: prechecks used all available training time')
        return 'skipped_budget'
    saved_segment = league.train_segment
    saved_gate = league.run_gate
    pause_path = run_dir / 'PAUSE_REQUESTED'

    def check_pause():
        if pause_path.exists():
            raise PauseRequested('Pause requested; PPO progress preserved through last saved rollout')

    def timed_train(*a, save_hook=None, **kwargs):
        check_pause()
        if time.monotonic() >= deadline:
            raise TimeBudgetReached('Training deadline before next segment')
        def after_save(steps):
            # auto_league.train_segment saves the model+critic+optimizers BEFORE this hook.
            if save_hook:
                save_hook(steps)
            atomic_json(run_dir / 'TRAIN_PROGRESS.json',
                        {'updated_utc':utc(), 'last_saved_decisions_this_cycle':steps,
                         'league_dir':str(league_dir), 'checkpoint':str(league_dir/'candidate.pt')})
            check_pause()
            if time.monotonic() >= deadline:
                raise TimeBudgetReached(f'Training budget reached safely after saved rollout ({steps} decisions)')
        return saved_segment(*a, save_hook=after_save, **kwargs)

    def timed_gate(*a, **kwargs):
        check_pause()
        if time.monotonic() >= deadline:
            raise TimeBudgetReached('Budget reached before another internal promotion gate')
        # A gate must complete before pausing: interrupted promotion is recoverable
        # but must not be interrupted by the PAUSE file halfway through.
        return saved_gate(*a, **kwargs)

    league.train_segment = timed_train
    league.run_gate = timed_gate
    argv = [
        '--source', str(base), '--data-dir', str(league_dir),
        '--max-cycles', '0', '--no-replays', '--device', 'cpu',
        '--seed', str(args.seed+400009),
        '--backup-minutes', '5',
        '--segment-decisions', str(args.segment_decisions),
        '--rollout', str(args.rollout), '--minibatch', str(min(128,args.rollout)),
        '--epochs', '2', '--eval-games', str(args.train_eval_games),
        '--eval-decisions', str(args.decisions),
    ]
    log('Training/resuming ISOLATED AutoLeague: ' + str(league_dir))
    log('Internal gate can promote isolated champion. Original data/autoleague will NOT be promoted.')
    try:
        league.main(argv)
        return 'returned'
    except TimeBudgetReached as exc:
        log(str(exc))
        return 'stopped_at_saved_boundary'
    except PauseRequested as exc:
        log(str(exc))
        return 'paused'
    finally:
        league.train_segment = saved_segment
        league.run_gate = saved_gate


def post_plan(args, seconds_left, pre_elapsed, pre_episodes, n_models, n_direct):
    # Adapt number of matches to remaining wall time to avoid an endless AFK run.
    sec_per_episode = max(0.10, pre_elapsed/max(pre_episodes,1))
    desired = 2 * (args.post_pairs*n_models + args.post_h2h_pairs*n_direct)
    budget = max(0.0, seconds_left - 45)
    scale = min(1.0, budget/max(1, desired*sec_per_episode*1.30))
    if budget < 60 or scale < 0.10:
        return 0, 0
    return max(4, int(args.post_pairs*scale)), max(4, int(args.post_h2h_pairs*scale))


def evaluate_post(inputs, league_dir, args, deadline, pre, log):
    from rlgym.rocket_league.sim import RocketSimEngine
    tests = dict(inputs)
    isolated_champ = league_dir / 'champion.pt'
    if isolated_champ.is_file():
        tests['trained_champion'] = isolated_champ
    candidate = league_dir / 'candidate.pt'
    if candidate.is_file():
        tests['training_candidate_in_progress'] = candidate
    # Don't count an identical model twice, using full content hash.
    found = {}
    for name,path in tests.items():
        found.setdefault(file_hash(path), (name,path))
    tests = {name:path for name,path in found.values()}
    selected = pre['selected_for_isolated_training']
    compared = [n for n in ('trained_champion','training_candidate_in_progress') if n in tests and n!=selected]
    left = deadline-time.monotonic()
    pairs, h2h_pairs = post_plan(args,left,pre['elapsed_seconds'],pre['episodes'],len(tests),len(compared))
    if pairs == 0:
        log('Not enough budget for reliable postcheck; snapshots remain safe for later benchmarking')
        return {'skipped': 'remaining wall-time too short', 'candidate_files': {n:str(p) for n,p in tests.items()}}
    teacher=NextoTeacher('cpu')
    engine=RocketSimEngine(rlbot_delay=False)
    vs_nexto={}
    direct={}
    try:
        cases=paired_cases(args.seed+500009,pairs)
        for name,path in tests.items():
            vs_nexto[name]=try_eval(path,teacher.actor,teacher,engine,cases,args.decisions,
                                    f'POST {name} vs Nexto',log)
        direct_cases=paired_cases(args.seed+600011,h2h_pairs)
        anchor_actor=league.actor_from(inputs[selected],'cpu')
        for name in compared:
            if file_hash(tests[name]) == file_hash(inputs[selected]):
                continue
            result=league.duel(league.actor_from(tests[name],'cpu'),anchor_actor,teacher,engine,
                               direct_cases,args.decisions,label=f'POST {name} vs starting {selected}')
            direct[name]=result
            log(f'POST {name} vs {selected}: {wld(result)} score={result["score"]:.3f}')
    finally:
        engine.close()
    return {
        'kind': 'afk_post_independent_first_goal', 'created_utc':utc(),
        'seed':args.seed, 'pairs_vs_nexto':pairs, 'pairs_head_to_head':h2h_pairs,
        'vs_nexto':vs_nexto, 'trained_vs_start':direct,
        'models':{n:{'checkpoint':str(p.relative_to(ROOT)),'sha256':file_hash(p)} for n,p in tests.items()},
        'leaderboard_vs_nexto':sorted(vs_nexto,key=lambda n:vs_nexto[n]['score'],reverse=True),
        'warning':'Post stage is exploratory: same evaluator and finite seeds, not full five-minute matches.'
    }


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--minutes',type=float,default=120)
    p.add_argument('--seed',type=int,default=86420513)
    p.add_argument('--decisions',type=int,default=750)
    p.add_argument('--pre-pairs',type=int,default=70)
    p.add_argument('--pre-h2h-pairs',type=int,default=24)
    p.add_argument('--post-pairs',type=int,default=60)
    p.add_argument('--post-h2h-pairs',type=int,default=35)
    p.add_argument('--segment-decisions',type=int,default=8192)
    p.add_argument('--rollout',type=int,default=512)
    p.add_argument('--train-eval-games',type=int,default=40)
    resume = p.add_mutually_exclusive_group()
    resume.add_argument('--resume-latest', action='store_true',
                        help='Resume the latest safely paused/interrupted AFK run; reuse its preliminary benchmark')
    resume.add_argument('--resume-run', type=Path,
                        help='Resume a specific AFK run directory in data/afk_runs')
    p.add_argument('--dry-run',action='store_true',help='Verify source models and league SHA, no simulation/training')
    p.add_argument('--smoke',action='store_true',help='Short functional test; do not treat as meaningful training')
    return p


def resumable_run(run_arg=None):
    """Select a previous paused/interrupted real run; never resume a completed job."""
    base = RUNS.resolve()
    choices = ([run_arg] if run_arg is not None else
               sorted((p for p in RUNS.iterdir() if p.is_dir()), reverse=True)
               if RUNS.exists() else [])
    for candidate in choices:
        candidate = Path(candidate).resolve()
        if candidate.parent != base:
            raise ValueError('Run must be directly inside data/afk_runs: ' + str(candidate))
        status_path = candidate / 'STATUS.json'
        if not status_path.exists():
            if run_arg is not None: raise ValueError('Missing STATUS.json in resume folder')
            continue
        status = read_json(status_path)
        if status.get('stage') not in ('paused', 'interrupted'):
            if run_arg is not None:
                raise ValueError('Can resume only paused/interrupted runs, not stage ' + str(status.get('stage')))
            continue
        if float(status.get('minutes_requested', 0)) < 15:
            if run_arg is not None: raise ValueError('Smoke runs are not resumable')
            continue
        if not all((candidate / x).is_file() for x in ('INPUTS.json','PRE_BENCHMARK.json')):
            if run_arg is not None: raise ValueError('Run has no complete preliminary benchmark / inputs')
            continue
        return candidate
    raise FileNotFoundError('No interrupted/paused AFK run with a completed PRE_BENCHMARK found')


def resume_inputs(run_dir, log):
    """Validate fixed SHA copies and reject unexpected main-league changes."""
    manifest = read_json(run_dir/'INPUTS.json')
    previous = read_json(run_dir/'STATUS.json')
    champion, statepath, state = require_league_state()
    if state.get('cycle') != previous.get('original_league_cycle'):
        raise RuntimeError('Main AutoLeague advanced since this run started; refusing resume')
    if not manifest or 'champion' not in manifest:
        raise ValueError('Missing champion in saved input manifest')
    if Path(manifest['champion']['source']).resolve() != champion.resolve():
        raise ValueError('Resume manifest references the wrong original champion')
    if file_hash(champion) != manifest['champion']['sha256']:
        raise RuntimeError('Original champion changed since paused run; refusing resume')
    inputs = {}
    for name, entry in manifest.items():
        path = (run_dir/'inputs'/f'{name}.pt').resolve()
        if path.parent != (run_dir/'inputs').resolve():
            raise ValueError('Unsafe input snapshot location')
        if path != Path(entry['copied_to']).resolve() or not path.is_file():
            raise ValueError('Snapshot is missing or moved: ' + name)
        if file_hash(path) != entry['sha256']:
            raise RuntimeError('Snapshot checksum failed: ' + name)
        inputs[name] = path
    pre = read_json(run_dir/'PRE_BENCHMARK.json')
    if pre.get('selected_for_isolated_training') not in inputs:
        raise RuntimeError('PRE selected model missing from immutable inputs')
    league_dir = run_dir/'league'
    if league_dir.exists():
        champ, league_state = league_dir/'champion.pt',league_dir/'league_state.json'
        if champ.exists() != league_state.exists():
            raise RuntimeError('Partial isolated league state. Stop and inspect; refusing reset')
        if league_state.is_file():
            saved = read_json(league_state)
            if saved.get('phase') not in ('train','promoting'):
                raise RuntimeError('Unknown isolated league phase')
            if saved.get('phase') == 'train' and file_hash(champ) != saved['champion_sha']:
                raise RuntimeError('Isolated league champion SHA mismatch')
    log('Resume source snapshots SHA checked; main champion+cycle unchanged')
    return inputs,pre,manifest,{str(champion):file_hash(champion),str(statepath):file_hash(statepath)}


def main(argv=None):
    args=parser().parse_args(argv)
    if args.smoke:
        args.minutes=6
        args.pre_pairs=2
        args.pre_h2h_pairs=2
        args.post_pairs=2
        args.post_h2h_pairs=2
        args.segment_decisions=512
        args.rollout=128
        args.train_eval_games=4
        args.decisions=180
    if not (1 <= args.minutes <= 1440):
        raise ValueError('--minutes must be 1 to 1440')
    if min(args.decisions,args.pre_pairs,args.pre_h2h_pairs,args.post_pairs,args.post_h2h_pairs,
           args.segment_decisions,args.rollout,args.train_eval_games) <= 0:
        raise ValueError('All evaluation counts and rollout lengths must be positive')
    if args.rollout>args.segment_decisions:
        raise ValueError('rollout must not exceed segment decisions')
    torch.set_num_threads(2)
    if args.dry_run:
        # Does not create a run directory or load RocketSim. Also checks main lock.
        with league.exclusive_league_lock(MAIN):
            sources, check, _ = choose_inputs(print)
        print('DRY RUN PASSED. Available:',', '.join(sources))
        print('Original champion SHA',check[str(MAIN/'champion.pt')])
        print('No training or simulation performed.')
        return 0

    RUNS.mkdir(parents=True, exist_ok=True)
    is_resume = args.resume_latest or args.resume_run is not None
    if is_resume:
        run_dir = resumable_run(args.resume_run if args.resume_run is not None else None)
    else:
        run_dir = RUNS / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        run_dir.mkdir(parents=True, exist_ok=False)
    log=Logger(run_dir / 'AFK_LOG.txt')
    start=time.monotonic()
    deadline=start+args.minutes*60
    reserve=min(18*60, args.minutes*60*0.22)
    train_deadline=deadline-reserve
    if is_resume:
        status = read_json(run_dir/'STATUS.json')
        status.pop('error',None)
        status['resume_count']=int(status.get('resume_count',0))+1
    else:
        status={'run_dir':str(run_dir),'created_utc':utc(),'minutes_requested':args.minutes,
                'stage':'starting','report_version':2,'original_untouched':None}
    status['pid']=os.getpid()
    status['session_minutes_requested']=args.minutes
    status['session_started_utc']=utc()
    def update(stage, **extra):
        status.update({'stage':stage, 'updated_utc':utc(), **extra})
        atomic_json(run_dir / 'STATUS.json',status)

    baseline_hashes={}
    log(('AFK RESUME' if is_resume else 'AFK NEW RUN') + ': no admin rights required. Leave window open.')
    log(f'Target {args.minutes:.1f} min this session; post-test reserve ~{reserve/60:.0f} min')
    try:
        # Existing main AutoLeague is exclusively locked while we train in a
        # separate sandbox; this prevents a competing normal training process.
        with league.exclusive_league_lock(MAIN):
            if is_resume:
                inputs,pre,manifest,baseline_hashes = resume_inputs(run_dir,log)
                old_pause=run_dir/'PAUSE_REQUESTED'
                if old_pause.exists():
                    old_pause.unlink()  # clearing only previous deliberate pause request
                update('training',pre_selected=pre['selected_for_isolated_training'])
                log('Resuming saved experiment WITHOUT repeating pre-benchmark.')
            else:
                sources, baseline_hashes, state = choose_inputs(log)
                inputs=keep_inputs(sources,run_dir)
                manifest={n:{'source':str(sources[n]),'copied_to':str(inputs[n]),'sha256':file_hash(inputs[n])} for n in inputs}
                atomic_json(run_dir/'INPUTS.json',manifest)
                update('precheck',original_league_cycle=state['cycle'], input_models=manifest)
                log('Main AutoLeague exclusively locked while AFK experiment runs')
                pre=evaluate_pre(inputs,args,log)
                atomic_json(run_dir/'PRE_BENCHMARK.json',pre)
                update('training',pre_selected=pre['selected_for_isolated_training'])
            if (run_dir/'PAUSE_REQUESTED').exists():
                raise PauseRequested('Pause requested at stage boundary')
            target=inputs[pre['selected_for_isolated_training']]
            isolated_dir=run_dir/'league'
            if time.monotonic() >= train_deadline:
                training_status='skipped_no_training_time'
            else:
                training_status=training_isolated(target,isolated_dir,args,train_deadline,log,run_dir)
            if training_status == 'paused':
                update('paused',training_status='paused',note='Safe saved PPO boundary; use RESUME launcher')
                log('PAUSED. Resume launcher can continue this run without repeating preliminary tests.')
                return_code=0
            else:
                update('postcheck',training_status=training_status)
                log('Training window ended. Starting held-out postchecks...')
                post=evaluate_post(inputs,isolated_dir,args,deadline,pre,log)
                atomic_json(run_dir/'POST_BENCHMARK.json',post)
                summary={'kind':'afk_2h_summary','created_utc':utc(),'run_dir':str(run_dir),
                         'session_wall_minutes':round((time.monotonic()-start)/60,2),
                         'resume_count':status.get('resume_count',0),
                         'model_trained_from':pre['selected_for_isolated_training'],
                         'training_status':training_status,
                         'starting_baseline_vs_nexto':pre['nexto_scores'][pre['selected_for_isolated_training']]['score'],
                         'post_ranking':post.get('leaderboard_vs_nexto',[]),
                         'post_scores':{n:round(r['score'],4) for n,r in post.get('vs_nexto',{}).items()},
                         'isolated_champion':str(isolated_dir/'champion.pt'),
                         'isolated_candidate_if_interrupted':str(isolated_dir/'candidate.pt'),
                         'original_champion_is_not_promoted':True,
                         'warnings':['First-goal benchmark, not five-minute games.',
                                     'Performance on finite evaluation seeds does not prove general superiority.',
                                     'Isolated champion promotions DO NOT affect data/autoleague.']}
                atomic_json(run_dir/'SUMMARY.json',summary)
                log('Complete! Report: ' + str(run_dir/'SUMMARY.json'))
                for name,score in summary['post_scores'].items():
                    log(f'  POST {name}: {score:.1%} vs Nexto')
                update('complete',summary=summary)
                return_code=0
    except PauseRequested as exc:
        log(str(exc))
        update('paused',training_status='paused',note='Stage boundary, no model overwritten')
        return_code=0
    except KeyboardInterrupt:
        log('Keyboard interrupted; latest fully completed PPO rollout is saved. Resume available.')
        update('interrupted',error='KeyboardInterrupt')
        return_code=130
    except Exception as exc:
        log(f'ERROR {type(exc).__name__}: {exc}')
        trace=traceback.format_exc()
        (run_dir/'ERROR_TRACEBACK.txt').write_text(trace,encoding='utf-8')
        print(trace,file=sys.stderr)
        update('error',error=f'{type(exc).__name__}: {exc}')
        return_code=1
    finally:
        if baseline_hashes:
            changed = [p for p,h in baseline_hashes.items() if not Path(p).is_file() or file_hash(Path(p)) != h]
            if changed:
                log('WARNING: Original files changed since run started: ' + str(changed))
                update('original_changed',original_untouched=False,changed_files=changed)
                return_code=2
            else:
                update(status['stage'],original_untouched=True)
                log('Verified: original champion, state and existing candidate hashes unchanged.')
        log('AFK outputs: ' + str(run_dir))
    return return_code


if __name__ == '__main__':
    raise SystemExit(main())
