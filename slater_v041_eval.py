"""Separate-process, read-only, paired 1v1 validation against six frozen bots."""
from __future__ import annotations
import argparse
from pathlib import Path
import torch
from slater_v041_core import atomic_json,read_json,sha256,validate_pool
from slater_v041_worker import paired_eval,load_pool


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',required=True)
    p.add_argument('--leader',required=True)
    p.add_argument('--manifest',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--seeds',type=int,default=2)
    p.add_argument('--steps',type=int,default=600)
    p.add_argument('--rlbot-delay',action=argparse.BooleanOptionalAction,default=True)
    args=p.parse_args(argv)
    if not (1<=args.seeds<=128 and 120<=args.steps<=4500
            and 1<=args.seed and args.seed+(args.seeds-1)*997<2**31-20000):
        p.error('Bad evaluation settings')
    root=Path.cwd().resolve()
    candidate=(root/args.candidate).resolve();leader=(root/args.leader).resolve()
    isolated=(root/'data/isolated').resolve()
    if not candidate.is_relative_to(isolated) or not leader.is_relative_to(isolated):
        raise ValueError('Evaluation policies must be isolated PPO checkpoints')
    report=(root/args.out).resolve()
    if not report.is_relative_to(isolated):raise ValueError('Evaluation report outside isolated directory')
    if report.exists():
        raise FileExistsError(f'Will not overwrite preexisting report: {report}')
    manifest=read_json(root/args.manifest)
    current=validate_pool(root,{'opponents':{k:v['path'] for k,v in manifest.items()}})
    if {k:v['sha256'] for k,v in current.items()} != {k:v['sha256'] for k,v in manifest.items()}:
        raise RuntimeError('An opponent changed after preflight')
    report_data=paired_eval(root,manifest,candidate,leader,seeds=args.seeds,
                            seed_base=args.seed,episode_steps=args.steps,rlbot_delay=args.rlbot_delay)
    result={'result':report_data,'candidate_sha':sha256(candidate),'leader_sha':sha256(leader),
            'manifest_sha':sha256(root/args.manifest),'status':'SIMULATOR_SCREEN_NOT_RLBOT_CHAMPION'}
    atomic_json(report,result)
    print('V041_EVAL',report_data['summary'],flush=True)
    print('V041_EVAL_REPORT',report,flush=True)

if __name__=='__main__':main()
