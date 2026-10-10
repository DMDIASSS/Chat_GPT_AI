"""Read-only finishing benchmark vs original Nexto, paired sides and seeds.

Scores are FIRST GOAL or short decision cap, NOT standard 5-minute matches.
Shot outcomes and backboard contacts are physics-based PROXIES, not labels.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json, random, hashlib
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
CHAMP=ROOT/'data'/'autoleague'/'champion.pt'
WAVE=ROOT/'data'/'mechanics'/'wavedash'/'last.pt'
CAND=ROOT/'data'/'finishing_lab'/'candidate.pt'
DEST=ROOT/'data'/'finishing_lab'/'reports'
EXPECTED='50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'


def score(outcomes):
    n=sum(outcomes.values())
    return (outcomes.get('ours',0)+.5*outcomes.get('draw',0))/n if n else 0.0


def run(args):
    from auto_league import actor_from, sha256, action_greedy, exclusive_league_lock
    from nexto_teacher import NextoTeacher
    from rlgym.rocket_league.sim import RocketSimEngine
    from finishing_match import FinishingMatch
    from finishing_scenarios import SCENARIOS
    if sha256(BASE)!=EXPECTED:
        raise RuntimeError('Cycle 9 checkpoint SHA mismatch. Refusing to benchmark unknown weights.')
    paths={'cycle09':BASE,'champion':CHAMP,'wavedash':WAVE}
    if CAND.is_file(): paths['finishing_candidate']=CAND
    if args.only_candidate:
        if not CAND.is_file():raise FileNotFoundError(CAND)
        paths={'cycle09':BASE,'finishing_candidate':CAND}
    manifest={label:{'path':str(p),'sha256':sha256(p)} for label,p in paths.items()}
    with exclusive_league_lock(ROOT/'data'/'autoleague'):
        # Avoid concurrent writes by an experimental trainer.
        with exclusive_league_lock(ROOT/'data'/'finishing_lab'):
            teacher=NextoTeacher('cpu')
            reference=teacher.actor
            models={label:actor_from(path) for label,path in paths.items()}
            engine=RocketSimEngine(rlbot_delay=False)
            try:
                results={}
                for case_ix,kind in enumerate(SCENARIOS):
                    print('\nSCENARIO',kind,flush=True)
                    for model_name,actor in models.items():
                        tally=Counter(); events=Counter(); decisions=0
                        # The very same test seeds are shared between different models.
                        random_plan=random.Random(f'{args.seed}:{case_ix}:{kind}')
                        seeds=[random_plan.randrange(1,2**31) for _ in range(args.pairs)]
                        for ii,seed in enumerate(seeds):
                            for orange in [False,True]:
                                random.seed(seed);np.random.seed(seed % 2**32)
                                m=FinishingMatch(teacher,engine,training_side_orange=orange,scenarios=kind)
                                winner='draw'
                                for _ in range(args.decisions):
                                    own,enemy=m.observe()
                                    a=action_greedy(actor,own)
                                    b=action_greedy(reference,enemy)
                                    _,done,winner=m.step(a,b,args.decisions)
                                    if done:break
                                tally[winner]+=1
                                decisions+=m.decisions
                                events.update(m.shot_tracker.counts)
                            if (ii+1)%max(1,args.pairs//4)==0:
                                print(f' {model_name}: {ii+1}/{args.pairs} pairs',flush=True)
                        result={'model':model_name,'scenario':kind,'pairs':args.pairs,
                                'episodes':2*args.pairs,'outcomes':dict(tally),
                                'score_vs_nexto':score(tally),'decision_ticks':decisions,
                                'shot_proxies':dict(events),
                                'seeds':seeds}
                        results[f'{model_name}/{kind}']=result
                        print(' ',model_name,'W/L/D',tally['ours'],tally['nexto'],tally['draw'],
                              'score',round(result['score_vs_nexto'],3),
                              'on_target',events['direct_on_target_proxy'],
                              'wall+followup',events['followup_on_target_proxy'],flush=True)
            finally: engine.close()
    report={'kind':'finishing_opportunities_v1','created_utc':datetime.now(timezone.utc).isoformat(),
            'seed':args.seed,'pairs_per_scenario':args.pairs,'decision_cap':args.decisions,
            'checkpoints':manifest,'scenarios':list(SCENARIOS),'results':results,
            'limitations':['first-goal / decision-cap, not 5-minute matches',
                           'shooting and rebound detection are coarse physics proxies',
                           'synthetic randomized starts do not represent real human replay states',
                           'no skill success is inferred from car rotations alone',
                           'evaluation alone never promotes a checkpoint']}
    DEST.mkdir(parents=True,exist_ok=True)
    dest=DEST/f'finishing_benchmark_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json'
    dest.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8')
    print('\nReport saved:',dest,flush=True)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pairs',type=int,default=8)
    p.add_argument('--decisions',type=int,default=330)
    p.add_argument('--seed',type=int,default=260103)
    p.add_argument('--only-candidate',action='store_true')
    args=p.parse_args(argv)
    if args.pairs<1 or args.decisions<1:p.error('counts must be positive')
    run(args)

if __name__=='__main__': main()
