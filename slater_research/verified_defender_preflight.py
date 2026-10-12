"""v0.1.8 read-only independent check of new defender environment.

For each selected train-split scenario, reproduce the goal twice with fresh
RocketSim arenas: once using the established v0.1.7 positive-control simulator,
once via VerifiedDefenderEnv. If the results do not agree, the scenario is NOT
approved for PPO. Never loads or writes Cycle 9, teacher, critic or actor.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from slater_research.counterfactual_audit import select_candidates, simulate
from slater_research.replay_engine import Clip
from slater_research.verified_defender_env import VerifiedDefenderEnv


def compare_results(reference: dict, new: dict, *, atol: float = .05) -> dict:
    # Comparisons are intentionally strict: same physics engine, starting
    # snapshot, inputs and scoring deadline must produce same goal outcome.
    src = reference.get('endpoint_error_uu')
    dst = new.endpoint_ball_error_uu
    peak = reference.get('peak_reference_error_uu')
    new_peak = new.peak_reference_error_uu
    def near(a,b):
        return (a is None and b is None) or (a is not None and b is not None and
               math.isfinite(a) and math.isfinite(b) and abs(a-b)<=atol)
    same = (bool(reference['attacker_scored']) == bool(new.attacker_scored) and
            bool(reference['defender_scored']) == bool(new.defender_scored) and
            reference['goal_step'] == new.goal_step and
            near(src,dst) and near(peak,new_peak))
    return {'same_as_v017':bool(same),
            'baseline_fidelity_pass':bool(reference['baseline_fidelity_pass']),
            'new_goal_status':new.status,
            'baseline_goal_step':reference['goal_step'],
            'new_goal_step':new.goal_step,
            'baseline_endpoint_error_uu':src,
            'new_endpoint_error_uu':dst,
            'baseline_peak_error_uu':peak,
            'new_peak_error_uu':new_peak}


def preflight_candidate(clip: Clip, candidate: dict, *, engine_factory,
                        max_error: float = 250.) -> dict:
    engine=engine_factory()
    try:
        prior=simulate(clip,candidate,'replay',engine=engine,max_error_uu=max_error)
    finally:
        engine.close()
    second=engine_factory()
    try:
        env=VerifiedDefenderEnv(clip,candidate,second,train_only=True)
        result=env.run_reference()
    finally:
        second.close()
    match=compare_results(prior,result)
    match['ready_for_counterfactual_investigation']=(
        match['same_as_v017'] and match['baseline_fidelity_pass'])
    return match


def run_preflight(clips: Path, catalog: dict, *, limit: int = 12,
                  engine_factory=None, progress=print):
    if engine_factory is None:
        from rlgym.rocket_league.sim import RocketSimEngine
        engine_factory=lambda:RocketSimEngine(rlbot_delay=False)
    if not clips.is_dir():raise FileNotFoundError(clips)
    selected=select_candidates(catalog,'train',limit)
    rows=[]
    for i,candidate in enumerate(selected,1):
        name=candidate['clip_file']
        row={'clip_file':name,'replay_sha256':candidate['replay_sha256'],'split':'train'}
        try:
            clip=Clip.load(clips/name)
            row.update(preflight_candidate(clip,candidate,engine_factory=engine_factory))
            row['status']=('consistent' if row['ready_for_counterfactual_investigation']
                           else 'not_reproduced_or_mismatch')
        except Exception as exc:
            row.update({'status':'error','error':f'{type(exc).__name__}: {exc}'})
        rows.append(row)
        progress(f'[{i}/{len(selected)}] {name}: {row["status"]}',flush=True)
    ready=sum(x['status']=='consistent' for x in rows)
    return {'schema_version':1,
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'purpose':'Goal-tail dynamic physics parity only; not PPO readiness',
            'warning':'A verified replay goal is NOT proof of a trainable save or a skilled defender. '
                      'No training/checkpoint files were accessed.',
            'summary':{'selected':len(selected),'ready_for_counterfactual_investigation':ready,
                       'not_reproduced_or_mismatch':sum(x['status']=='not_reproduced_or_mismatch' for x in rows),
                       'errors':sum(x['status']=='error' for x in rows)},
            'cases':rows}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--clips',required=True)
    p.add_argument('--catalog',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--limit',type=int,default=12)
    p.add_argument('--max-error',type=float,default=250.)
    args=p.parse_args(argv)
    if args.limit<1 or not math.isfinite(args.max_error) or args.max_error<=0:
        p.error('Invalid limit or max-error')
    dst=Path(args.out)
    if dst.exists() or dst.with_name(dst.name+'.partial').exists():
        p.error('Output already exists; refuse overwrite')
    with Path(args.catalog).open('r',encoding='utf-8') as f:catalog=json.load(f)
    report=run_preflight(Path(args.clips),catalog,limit=args.limit)
    dst.parent.mkdir(parents=True,exist_ok=True)
    partial=dst.with_name(dst.name+'.partial')
    with partial.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2,allow_nan=False)
    os.replace(partial,dst)
    print('SUMMARY '+str(report['summary']))
    print('READ ONLY: does not train, copy or modify checkpoints.')
    return report


if __name__=='__main__':main()
