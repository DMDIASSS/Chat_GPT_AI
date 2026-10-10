"""Isolated tactical balance PPO: preserve Cycle9, finishing lab and main league.

No automatic promotion. Runs small learning rates and original-policy KL anchor.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
SHA='50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
MAIN=ROOT/'data'/'autoleague'
TARGET=ROOT/'data'/'tactical_balance'
SMOKE=ROOT/'data'/'tactical_balance_smoke'


def run(args):
    import torch
    import auto_league as league
    from nexto_teacher import NextoTeacher
    from balance_match import BalanceMatch
    if not SOURCE.is_file() or league.sha256(SOURCE)!=SHA:raise RuntimeError('Cycle9 missing or changed')
    if not (MAIN/'champion.pt').is_file() or not (MAIN/'league_state.json').is_file():
        raise RuntimeError('Main league files missing')
    if args.device=='cuda:0' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    hashes={n:league.sha256(MAIN/n) for n in ['champion.pt','league_state.json']}
    target=SMOKE if args.mode=='smoke' else TARGET
    if args.mode=='smoke':
        args.steps=min(args.steps,96);args.rollout=min(args.rollout,48)
        args.games=min(args.games,4);args.decisions=min(args.decisions,90)
    if args.mode=='check':
        from rlgym.rocket_league.sim import RocketSimEngine
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            teacher=NextoTeacher('cpu')
            match=BalanceMatch(teacher,engine,scenarios='grounded')
            actor=league.actor_from(SOURCE,'cpu')
            a,b=match.observe()
            result=match.step(league.action_greedy(actor,a),league.action_greedy(teacher.actor,b),12)
            print('One real RocketSim step:',result,flush=True)
        finally:engine.close()
        return
    with league.exclusive_league_lock(MAIN):
        with league.exclusive_league_lock(target):
            teacher=NextoTeacher('cpu')
            src=league.actor_from(SOURCE,'cpu')
            dst=target/'candidate.pt'
            if args.mode in ('train','smoke'):
                torch.set_num_threads(2)
                actor,critic,ao,co,current,parent=league.start_candidate(
                    SOURCE,dst,args.device,cycle=1,seed=args.seed,actor_lr=8e-7,critic_lr=2e-4)
                original_match=league.Match
                league.Match=BalanceMatch
                try:
                    while current<args.steps:
                        n=min(args.steps-current,args.rollout*4)
                        config=argparse.Namespace(seed=args.seed,device=args.device,
                            segment_decisions=n,rollout=args.rollout,minibatch=min(128,args.rollout),
                            epochs=2,episode_decisions=450,temperature=.85,clip=.08,
                            anchor=1.4,entropy=.001)
                        current,stats=league.train_segment(config,actor,critic,ao,co,src,
                            teacher.actor,teacher,existing=dst,current=current,cycle=1,parent_sha=parent)
                        league.atomic_json(target/'progress.json',{
                            'source_sha':SHA,'candidate_sha':league.sha256(dst),
                            'decisions':current,'target':args.steps,'rollout':args.rollout,
                            'last_chunk':stats,'at':datetime.now(timezone.utc).isoformat()})
                        print('Balance PPO saved:',current,'/',args.steps,flush=True)
                finally:league.Match=original_match
            if not dst.is_file():raise FileNotFoundError('No tactical_balance candidate yet')
            result=league.run_gate(league.actor_from(dst,'cpu'),src,teacher.actor,teacher,
                        games=args.games, decisions=args.decisions,seed=args.seed+754323)
            result.update({'source_sha':SHA,'candidate_sha':league.sha256(dst),'experimental':True,
                'notice':'No automatic promotion. Review also shooting/defense metrics.'})
            path=target/'reports'/f'eval_{league.timestamp()}.json'
            league.atomic_json(path,result)
            print('Result written:',path,'verdict:',result['verdict'],flush=True)
    for n,h in hashes.items():
        if league.sha256(MAIN/n)!=h:raise RuntimeError('Main league file changed unexpectedly: '+n)
    print('Main champion and league state hashes unchanged.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['check','smoke','train','eval'],default='check')
    p.add_argument('--steps',type=int,default=8192)
    p.add_argument('--rollout',type=int,default=256)
    p.add_argument('--games',type=int,default=80)
    p.add_argument('--decisions',type=int,default=750)
    p.add_argument('--seed',type=int,default=851003)
    p.add_argument('--device',choices=['cpu','cuda:0'],default='cpu')
    args=p.parse_args()
    if min(args.steps,args.rollout,args.games,args.decisions)<=0:p.error('positive counts required')
    run(args)
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        print('Stopped. Already completed rollouts remain saved. Re-run BALANCE_2_TRAIN.bat to continue.')
        raise SystemExit(130)
