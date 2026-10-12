"""Slater v0.3.0 — read-only MULTI-GOAL 5-minute RocketSim approximate match eval.

Checks original Cycle9 and v0.2.7 candidates against unchanged Nexto, each
policy playing both sides and seeded identically at kickoff. Reinitializes
RocketSim at every goal; no goal celebration, no RLBot game process, limited
overtime. Thus comparable between checkpoints but NOT equivalent to the user's
original RLBot full-match 58.6% benchmark.

No training, no checkpoint promotion. Imports the existing Slater environment.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired
import slater_nexto_heldout_eval_v028 as heldout

NEXTOSHA = paired.EXPECTED_NEXTO_SHA256
TICKS_PER_ACTION = base.ACTION_REPEAT
FPS = 120


def kickoff_seed(match_seed: int, goal_index: int) -> int:
    if match_seed <= 0 or goal_index < 0:
        raise ValueError('Invalid match seed/index')
    return 1 + ((match_seed + goal_index * 104729 - 1) % (2**31 - 2))


def seeded_reset(env, seed: int):
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    obs = env.reset(seed)
    return obs, heldout.kickoff_signature(env)


def one_full_match(env, actor, match_seed: int, side: str, regulation_steps: int,
                   overtime_steps: int = 0):
    """Clock is in simulation actions (8 ticks/step). No ball/goal cutscene."""
    if side not in ('blue','orange') or min(regulation_steps, match_seed) < 1 or overtime_steps < 0:
        raise ValueError('Invalid match configuration')
    # The evaluation controls timeout explicitly via env.max_steps on each new kickoff.
    clock = 0
    score = 0
    conceded = 0
    touches = 0
    opponent_touches = 0
    kickoff_idx = 0
    goal_events = []
    overtime_started = False
    overtime_used = False
    obs, opening_fingerprint = seeded_reset(env, kickoff_seed(match_seed, kickoff_idx))
    while True:
        target = regulation_steps + (overtime_steps if overtime_started else 0)
        env.max_steps = env.t + (target - clock)
        if clock >= target:
            if not overtime_started and score == conceded and overtime_steps:
                overtime_started = True
                overtime_used = True
                continue
            break
        act = paired.greedy_action(actor, obs, env.device)
        obs, _, done, info = env.step(act)
        clock += 1
        if not done:
            continue
        touches += int(info['student_touches'])
        opponent_touches += int(info['opponent_touches'])
        outcome = int(info['outcome'])
        if outcome not in (-1, 0, 1):
            raise RuntimeError(f'Invalid outcome {outcome}')
        if outcome:
            score += (outcome == 1)
            conceded += (outcome == -1)
            goal_events.append({'step':clock,'scorer':('student' if outcome == 1 else 'nexto'),
                                'student_goals':score,'nexto_goals':conceded})
            if overtime_started or clock >= regulation_steps:
                # Regulation-ending goal still counts. A tie here can enter overtime.
                if overtime_started:
                    break
            kickoff_idx += 1
            obs, _ = seeded_reset(env, kickoff_seed(match_seed, kickoff_idx))
        elif not info['timeout']:
            raise RuntimeError('Episode ended without goal/timeout')
        # For a regulation-time timeout the next loop activates overtime without
        # resetting, preserving actual positions and velocities.
        if clock >= target:
            if not overtime_started and score == conceded and overtime_steps:
                overtime_started = True
                overtime_used = True
            else:
                break
    return {'seed':match_seed,'side':side,'goals_for':score,'goals_against':conceded,
            'goal_diff':score-conceded,'outcome':int(np.sign(score-conceded)),
            'draw':score == conceded, 'decisions':clock,
            'touches':touches,'opponent_touches':opponent_touches,
            'kickoffs':kickoff_idx+1,'first_kickoff_signature':opening_fingerprint,
            'overtime':overtime_used,'goal_events':goal_events}


def fingerprint_equal(a, b):
    return a['seed']==b['seed'] and a['side']==b['side'] and a['first_kickoff_signature']==b['first_kickoff_signature']


def match_equal(a, b):
    fields=('seed','side','goals_for','goals_against','goal_diff','outcome','decisions',
            'touches','opponent_touches','kickoffs','first_kickoff_signature','overtime','goal_events')
    return all(a[k]==b[k] for k in fields)


def aggregate(rows):
    n=len(rows)
    if not n: raise ValueError('Empty match list')
    wins=sum(r['outcome']==1 for r in rows)
    losses=sum(r['outcome']==-1 for r in rows)
    draws=n-wins-losses
    return {'matches':n,'wins':wins,'losses':losses,'draws':draws,
            'win_rate':round(wins/n,5), 'points_rate':round((wins+.5*draws)/n,5),
            'avg_goals_for':round(float(np.mean([r['goals_for'] for r in rows])),4),
            'avg_goals_against':round(float(np.mean([r['goals_against'] for r in rows])),4),
            'avg_goal_diff':round(float(np.mean([r['goal_diff'] for r in rows])),4),
            'avg_touches':round(float(np.mean([r['touches'] for r in rows])),3),
            'avg_opponent_touches':round(float(np.mean([r['opponent_touches'] for r in rows])),3),
            'overtime_matches':sum(r['overtime'] for r in rows)}


def compare_by_seed(records, candidate_name):
    """Bootstrap across paired match seeds, treating Blue+Orange as one sample."""
    by_key={(r['policy'],r['seed'],r['side']):r for r in records}
    seeds=sorted({r['seed'] for r in records})
    samples={'win_rate':[], 'points_rate':[], 'goal_diff':[]}
    for seed in seeds:
        pairs=[]
        for side in ('blue','orange'):
            baseline=by_key[('original',seed,side)]
            candidate=by_key[(candidate_name,seed,side)]
            def value(r,kind):
                if kind=='win_rate':return float(r['outcome']==1)
                if kind=='points_rate':return 1. if r['outcome']==1 else (.5 if r['outcome']==0 else 0.)
                return float(r['goal_diff'])
            pairs.append({k:value(candidate,k)-value(baseline,k) for k in samples})
        for k in samples:
            samples[k].append((pairs[0][k]+pairs[1][k])/2.)
    return {k:paired.paired_interval(v) for k,v in samples.items()}


def run_matches(actors, nexto, actions, observer, seed_count, seed_base, reg_steps, ot_steps):
    envs={'blue':base.Native1v1(actions,observer,nexto,max_steps=reg_steps,device='cpu'),
          'orange':paired.RoleSwap1v1(actions,observer,nexto,max_steps=reg_steps,device='cpu')}
    records=[]
    probe={}
    try:
        for side,env in envs.items():
            first=one_full_match(env,actors['original'],seed_base,side,reg_steps,ot_steps)
            repeat=one_full_match(env,actors['original'],seed_base,side,reg_steps,ot_steps)
            if not match_equal(first,repeat):
                raise RuntimeError('NONDETERMINISTIC_MATCH ' + json.dumps({'first':first,'repeat':repeat}))
            probe[side]=first
        print('DETERMINISM_CHECK PASS (repeat full match; both sides)',flush=True)
        for i in range(seed_count):
            seed=seed_base + 997*i
            for side,env in envs.items():
                baseline=None
                for name,actor in actors.items():
                    row=one_full_match(env,actor,seed,side,reg_steps,ot_steps)
                    if baseline is not None and not fingerprint_equal(row,baseline):
                        raise RuntimeError(f'UNMATCHED_KICKOFF seed={seed} side={side} policy={name}')
                    if baseline is None: baseline=row
                    row['policy']=name
                    records.append(row)
            if (i+1)%4==0 or i+1==seed_count:
                print(f'PROGRESS {i+1}/{seed_count} match seeds complete',flush=True)
        for side,env in envs.items():
            repeat=one_full_match(env,actors['original'],seed_base,side,reg_steps,ot_steps)
            if not match_equal(probe[side],repeat):
                raise RuntimeError('BASELINE_DRIFT_AFTER_EVAL side='+side)
        print('END_DETERMINISM_CHECK PASS',flush=True)
    finally:
        for env in envs.values():env.close()
    overall={name:aggregate([r for r in records if r['policy']==name]) for name in actors}
    by_side={name:{side:aggregate([r for r in records if r['policy']==name and r['side']==side])
                   for side in ('blue','orange')} for name in actors}
    paired_results={name:compare_by_seed(records,name) for name in actors if name!='original'}
    return {'overall':overall,'by_side':by_side,'paired_vs_original':paired_results,'records':records}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True,help='v027 checkpoint to evaluate; suggest u60')
    p.add_argument('--extra',action='append',default=[],help='Additional checkpoints to compare')
    p.add_argument('--seeds',type=int,default=8)
    p.add_argument('--seed',type=int,default=1876359103)
    p.add_argument('--regulation-seconds',type=int,default=300)
    p.add_argument('--overtime-seconds',type=int,default=120)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    if not (2 <= args.seeds <= 128 and 1 <= args.seed < 2**31-128000 and
            10 <= args.regulation_seconds <= 300 and 0<=args.overtime_seconds <= 300 and
            len(args.extra)<=3):
        p.error('Limits: seeds 2..128, regulation 10..300s, overtime 0..300s, <=3 extras')
    root=Path.cwd().resolve()
    output=base.check_output(args.out,root,'.json')
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA,cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    source=root/CYCLE9
    nexto_source=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_source)!=NEXTOSHA:
        raise RuntimeError('Original Cycle9 or vendor Nexto checksum guard mismatch')
    candidates=[heldout.checked_candidate(path,root,CYCLE9_SHA,NEXTOSHA)
                for path in [args.checkpoint]+args.extra]
    if any(doc.get('meta', {}).get('nexto_sha') != NEXTOSHA for _,doc in candidates):
        raise ValueError('Candidate missing Nexto provenance')
    if len({str(path) for path,_ in candidates})!=len(candidates):
        raise ValueError('Duplicate candidate checkpoints')
    torch.set_num_threads(2)
    _,cycle9=cycle9_pair(root)
    cycle9.eval()
    actors={'original':cycle9}
    provenance={}
    for path,doc in candidates:
        model,_=cycle9_pair(root)
        model.load_state_dict(doc['actor'],strict=True)
        model.eval()
        label='u'+str(doc['global_updates'])
        if label in actors:raise ValueError('Duplicate model update labels')
        actors[label]=model
        provenance[label]={'source':str(path),'sha256':base.sha256(path),
                           'global_updates':doc['global_updates']}
    for model in actors.values():
        for param in model.parameters():param.requires_grad_(False)
    nexto=torch.jit.load(str(nexto_source),map_location='cpu')
    nexto.eval()
    for param in nexto.parameters():param.requires_grad_(False)
    lookup=nexto_actions()
    actions=np.stack([np.asarray(lookup[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape!=(90,8) or not np.isfinite(actions).all():
        raise RuntimeError('Nexto action table invalid')
    reg_steps=args.regulation_seconds*FPS//TICKS_PER_ACTION
    ot_steps=args.overtime_seconds*FPS//TICKS_PER_ACTION
    started=time.perf_counter()
    print('REAL_ROCKETSIM_MULTIGOAL_MATCH_COMPARE read-only, source-protected',flush=True)
    print('REGULATION',args.regulation_seconds,'s OVERTIME_CAP',args.overtime_seconds,
          's SEEDS',args.seeds,'BOTH_SIDES POLICIES',list(actors),flush=True)
    result=run_matches(actors,nexto,actions,TeamObserver(),args.seeds,args.seed,reg_steps,ot_steps)
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_source)!=NEXTOSHA:
        raise RuntimeError('Protected source SHA changed; refusing report')
    report={'schema_version':1, 'description':'Multi-goal RocketSim 1v1, regulation+bounded overtime, simulated kickoff resets. NOT real RLBot full matches.',
            'regulation_seconds':args.regulation_seconds,'overtime_cap_seconds':args.overtime_seconds,
            'seed_base':args.seed,'seed_count':args.seeds,'sides':2,
            'original_cycle9_sha256':CYCLE9_SHA,'nexto_sha256':NEXTOSHA,
            'candidates':provenance,'elapsed_seconds':round(time.perf_counter()-started,3),**result}
    print('OVERALL',json.dumps(result['overall'],sort_keys=True),flush=True)
    print('PAIRED_VS_ORIGINAL',json.dumps(result['paired_vs_original'],sort_keys=True),flush=True)
    print('BY_SIDE',json.dumps(result['by_side'],sort_keys=True),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
    print('SAVED_READ_ONLY_REPORT',output,'NO_CHECKPOINT_CHANGES',flush=True)

if __name__=='__main__':main()
