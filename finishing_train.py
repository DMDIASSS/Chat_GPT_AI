"""ISOLATED, pause/resume-friendly native Nexto PPO finishing experiment.

Does not alter original champion, original Nexto, AutoLeague history or source.
Uses existing AutoLeague PPO implementation, with an in-process FinishingMatch
that introduces diverse attacking opportunities and tiny conditional bonuses.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
SHA='50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
MAIN=ROOT/'data'/'autoleague'
TRAIN=ROOT/'data'/'finishing_lab'
SMOKE=ROOT/'data'/'finishing_lab_smoke'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['check','smoke','train','eval'],default='check')
    p.add_argument('--steps',type=int,default=8192,help='cumulative PPO decision ticks in this experiment')
    p.add_argument('--rollout',type=int,default=256)
    p.add_argument('--episode-decisions',type=int,default=360)
    p.add_argument('--eval-decisions',type=int,default=450)
    p.add_argument('--eval-games',type=int,default=40)
    p.add_argument('--seed',type=int,default=20261113)
    p.add_argument('--device',choices=['cpu','cuda:0'],default='cpu')
    args=p.parse_args(argv)
    if min(args.steps,args.rollout,args.episode_decisions,args.eval_decisions,args.eval_games)<1:
        p.error('all counts must be positive')

    import torch
    import auto_league as league
    from auto_league import sha256, exclusive_league_lock
    from native_nexto import SOURCE_MODEL
    if not SOURCE.is_file() or sha256(SOURCE)!=SHA:
        raise RuntimeError('Missing or modified Cycle 9 source checkpoint: refusing to proceed')
    if not SOURCE_MODEL.exists():raise FileNotFoundError(SOURCE_MODEL)
    if not (MAIN/'champion.pt').exists() or not (MAIN/'league_state.json').exists():
        raise RuntimeError('Main champion and league state missing; check project installation')
    main_state=json.loads((MAIN/'league_state.json').read_text(encoding='utf8'))
    if main_state.get('phase')!='train' or main_state.get('champion_sha')!=sha256(MAIN/'champion.pt'):
        raise RuntimeError('Main AutoLeague champion/state mismatch or incomplete promotion. Resolve first.')
    if args.device=='cuda:0' and not torch.cuda.is_available():
        raise RuntimeError('CUDA device unavailable')
    target=SMOKE if args.mode=='smoke' else TRAIN
    orig_champion=sha256(MAIN/'champion.pt')
    orig_league=sha256(MAIN/'league_state.json')
    print('Mode:',args.mode,'source:',SOURCE,'SHA:',SHA[:16])
    print('Original champion SHA:',orig_champion[:16])
    print('Experiment output:',target)
    if args.mode=='check':
        # Don't modify any checkpoints in this mode. Real simulator sanity check.
        from nexto_teacher import NextoTeacher
        from rlgym.rocket_league.sim import RocketSimEngine
        from finishing_match import FinishingMatch
        teacher=NextoTeacher('cpu')
        candidate_actor=league.actor_from(SOURCE,'cpu')
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            for kind in ['ground_finish','flick_setup','backboard_setup','defender_block']:
                m=FinishingMatch(teacher,engine,scenarios=kind)
                assert len(m.state.cars)==2
                a,b=m.observe()
                own=league.action_greedy(candidate_actor,a)
                opp=league.action_greedy(teacher.actor,b)
                reward,done,winner=m.step(own,opp,4)
                assert isinstance(reward,float) and winner in ('ours','nexto','draw')
                print('Scenario and physics step OK:',kind)
        finally:engine.close()
        print('Preflight passed. No weights or league state modified.')
        return
    with exclusive_league_lock(MAIN):
        # Main AutoLeague remains blocked from starting while experiment active.
        with exclusive_league_lock(target):
            if args.mode in ('train','smoke'):
                if args.mode=='smoke':
                    args.steps=min(args.steps,96)
                    args.rollout=min(args.rollout,48)
                    args.eval_games=min(args.eval_games,4)
                    args.eval_decisions=min(args.eval_decisions,90)
                train(args,league,target)
            else:
                evaluate(args,league,target)
    # These assertions flag unexpected external changes; neither training nor
    # evaluation writes either source file.
    if sha256(MAIN/'champion.pt')!=orig_champion or sha256(MAIN/'league_state.json')!=orig_league:
        raise RuntimeError('ALERT: main league files changed during experiment. Investigate before continuing.')
    print('Main AutoLeague champion and state SHA unchanged.')


def evaluate(args,league,target):
    from nexto_teacher import NextoTeacher
    output=target/'candidate.pt'
    if not output.exists():raise FileNotFoundError(f'No experiment candidate at {output}')
    teacher=NextoTeacher('cpu')
    baseline=league.actor_from(SOURCE,'cpu')
    candidate=league.actor_from(output,'cpu')
    result=league.run_gate(candidate,baseline,teacher.actor,teacher,
                           games=args.eval_games, decisions=args.eval_decisions,
                           seed=args.seed+988997)
    result.update({'source_sha':SHA,'candidate_sha':league.sha256(output),
                   'notice':'This is an experimental result; NO automatic promotion performed.'})
    report_path=target/'reports'/f'eval_{league.timestamp()}.json'
    league.atomic_json(report_path,result)
    print('Evaluation report:',report_path,'verdict:',result['verdict'])
    print('Do not replace your champion from this result alone.')


def train(args,league,target):
    from nexto_teacher import NextoTeacher
    from finishing_match import FinishingMatch
    import torch
    torch.set_num_threads(2)
    target.mkdir(parents=True,exist_ok=True)
    checkpoint=target/'candidate.pt'
    actor,critic,ao,co,current,parent=league.start_candidate(
        SOURCE,checkpoint,args.device,cycle=1,seed=args.seed,
        actor_lr=1.0e-6,critic_lr=2.0e-4)
    print('Resuming isolated finishing PPO from',current,'/',args.steps,'decision ticks.')
    teacher=NextoTeacher('cpu')
    original=league.actor_from(SOURCE,'cpu')
    if current>=args.steps:
        print('Target steps already reached. Evaluation only.')
        evaluate(args,league,target)
        return
    # Change Match dependency in memory ONLY. The source auto_league.py on disk
    # and all its regular behavior remain unchanged.
    original_match=league.Match
    league.Match=FinishingMatch
    try:
        while current<args.steps:
            n=min(args.steps-current,args.rollout*4)
            chunk=argparse.Namespace(seed=args.seed,device=args.device,
                  segment_decisions=n,rollout=args.rollout,minibatch=min(128,args.rollout),
                  epochs=2,episode_decisions=args.episode_decisions,temperature=.85,
                  clip=.08,anchor=1.0,entropy=.001)
            current,stats=league.train_segment(chunk,actor,critic,ao,co,
                original,teacher.actor,teacher,existing=checkpoint,
                current=current,cycle=1,parent_sha=parent)
            league.atomic_json(target/'progress.json',{
                'source_sha':SHA,'candidate_sha':league.sha256(checkpoint),
                'decisions':current,'goal_decisions':args.steps,
                'completed_utc':datetime.now(timezone.utc).isoformat(),
                'last_chunk':stats,'experimental':True})
            print('Finishing progress:',current,'/',args.steps,'(safe to pause between rollouts)',flush=True)
    finally:
        league.Match=original_match
    print('Training complete; starting GENERAL-PLAY evaluation against original Nexto and Cycle 9.')
    evaluate(args,league,target)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        print('\nInterrupted. Last completed PPO rollout was saved. Use FINISH_2_TRAIN.bat to resume.')
        raise SystemExit(130)
