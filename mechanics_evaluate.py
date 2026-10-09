"""Paired mechanic-success evaluation and optional frozen Nexto competitive guardrail.
No training and no checkpoint modification.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import random
from pathlib import Path
import numpy as np
import torch
from mechanics_train import ROOT, DEFAULT_SOURCE, load_actor
from mechanics_scenarios import STAGES
from mechanics_tasks import MechanicsMatch
from nexto_teacher import NextoTeacher
from native_nexto import select_action, evaluation


def stage_eval(actor, teacher, stage, *, episodes=12, seed=123, max_steps=120,
               opponent='passive'):
    from rlgym.rocket_league.sim import RocketSimEngine
    torch.set_num_threads(2)
    random.seed(seed)
    np.random.seed(seed)
    engine = RocketSimEngine(rlbot_delay=False)
    result = {'attempts':episodes, 'successes':0, 'mean_success_decisions':None,
              'touch_events':0, 'goal_for':0, 'goal_against':0,
              'decisions':0, 'success_steps':[], 'reward_total':0.}
    actor.eval()
    try:
        for n in range(episodes):
            match = MechanicsMatch(teacher, engine, stage, seed=seed+n,
                     orange=bool(n%2),opponent=opponent, max_steps=max_steps)
            for _ in range(max_steps):
                our_view, other_view = match.observe()
                action, _, _ = select_action(actor, our_view, 'cpu', sample=False)
                if opponent == 'nexto':
                    theirs = teacher.logits([(other_view[1], other_view[2], other_view[3])])
                    other_action = int(theirs[0].argmax())
                else:
                    other_action = 0
                reward, done, success = match.step(action, other_action)
                result['reward_total'] += reward
                if done:
                    break
            t = match.tracker
            result['decisions'] += t.t
            result['touch_events'] += t.touch_events
            result['successes'] += int(t.success)
            if t.success:
                result['success_steps'].append(t.success_time)
            goal = bool(getattr(match.state, 'goal_scored',False))
            if goal:
                scorer = (float(match.state.ball.position[1]) > 0.) != match.our_orange
                result['goal_for' if scorer else 'goal_against'] += 1
            print(f'{stage} {n+1}/{episodes}: success={success} decisions={t.t} touches={t.touch_events}',flush=True)
    finally:
        engine.close()
    times = result.pop('success_steps')
    result['mean_success_decisions'] = round(float(np.mean(times)),2) if times else None
    result['success_pct'] = round(100*result['successes']/episodes,2)
    result['reward_total']=round(result['reward_total'],3)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',choices=STAGES,required=True)
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--candidate',type=Path,default=None)
    p.add_argument('--episodes',type=int,default=12)
    p.add_argument('--seed',type=int,default=741)
    p.add_argument('--episode-decisions',type=int,default=100)
    p.add_argument('--opponent',choices=['passive','nexto'],default='passive')
    p.add_argument('--competitive',action='store_true',help='also do paired first-to-goal evaluation vs frozen Nexto')
    p.add_argument('--competitive-games',type=int,default=12)
    args=p.parse_args()
    if args.episodes < 1 or args.episode_decisions < 1 or args.competitive_games < 1:
        p.error('episode and game counts must be positive')
    cand=args.candidate or ROOT/'data'/'mechanics'/args.stage/'last.pt'
    if not cand.exists() or not args.source.exists():
        p.error(f'Missing candidate {cand} or baseline {args.source}')
    base=load_actor(args.source,'cpu')
    candidate=load_actor(cand,'cpu')
    # Use paired, identical seeds, with alternation of sides.
    teacher=NextoTeacher('cpu')
    print('MECHANIC BASELINE',args.stage,flush=True)
    orig=stage_eval(base,teacher,args.stage, episodes=args.episodes,
           seed=args.seed,max_steps=args.episode_decisions,opponent=args.opponent)
    print('MECHANIC CANDIDATE',args.stage,flush=True)
    tuned=stage_eval(candidate,teacher,args.stage, episodes=args.episodes,
           seed=args.seed,max_steps=args.episode_decisions,opponent=args.opponent)
    results={'stage':args.stage,'source':str(args.source.resolve()),'candidate':str(cand.resolve()),
             'seed':args.seed, 'baseline':orig, 'candidate_stats':tuned,
             'warning':'Mechanic success criteria are training proxies, NOT verified advanced gameplay.'}
    print(f'\nSUCCESS: baseline {orig["successes"]}/{args.episodes} vs candidate '
          f'{tuned["successes"]}/{args.episodes}',flush=True)
    if args.competitive:
        print('\nCOMPETITIVE GUARDRAIL: baseline vs frozen Nexto',flush=True)
        b=evaluation(base,teacher,'cpu',games=args.competitive_games,
                     decisions=750,seed=args.seed)
        print('\nCOMPETITIVE GUARDRAIL: candidate vs frozen Nexto',flush=True)
        c=evaluation(candidate,teacher,'cpu',games=args.competitive_games,
                     decisions=750,seed=args.seed)
        results['competitive_baseline']=b
        results['competitive_candidate']=c
        print('Warning: small first-to-score samples are NOT full-match skill rankings.')
    out=ROOT/'data'/'mechanics'/args.stage/'evaluations'
    out.mkdir(parents=True,exist_ok=True)
    target=out / f'paired_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    target.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(f'Saved read-only evaluation results to {target}')
    print('Only manually promote a candidate that improves mechanics without losing competitive ability.')

if __name__=='__main__':
    main()
