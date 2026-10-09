"""Read-only eval smoke test of existing AutoLeague champion and candidate.

Exercises actual RocketSim, Nexto observations, the evaluator fingerprint and
report JSON encoding. Does NOT train, write models, promote or blacklist.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import torch
from auto_league import ROOT, DATA, actor_from, run_gate, sha256, safe_load, strict_json_dumps, log
from nexto_teacher import NextoTeacher


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,default=DATA)
    p.add_argument('--games',type=int,default=8)
    p.add_argument('--decisions',type=int,default=180)
    args=p.parse_args()
    if args.games<1 or args.decisions<1: raise ValueError('games and decisions must be positive')
    data=args.data_dir.resolve()
    champ=data/'champion.pt'
    cand=data/'candidate.pt'
    statefile=data/'league_state.json'
    if not (champ.is_file() and cand.is_file() and statefile.is_file()):
        raise FileNotFoundError(f'Expected champion.pt, candidate.pt and league_state.json under {data}')
    state=json.loads(statefile.read_text(encoding='utf8'))
    if state.get('phase')!='train':
        raise RuntimeError('League currently has an interrupted promotion; use AUTO_1_START to recover it first.')
    if sha256(champ)!=state['champion_sha']:
        raise RuntimeError('Champion hash mismatch. Aborting without changing anything.')
    cand_meta=safe_load(cand)
    if cand_meta.get('parent_sha')!=sha256(champ) or cand_meta.get('league_cycle')!=state['cycle']:
        raise RuntimeError('Candidate checkpoint belongs to another champion/cycle. Not evaluating mismatched files.')
    torch.set_num_threads(2)
    log('READ-ONLY: No training, writes, rollback, promotion, or model changes.')
    log(f'Champion={sha256(champ)[:12]}, Candidate steps={cand_meta.get("timesteps", "?")}.')
    teacher=NextoTeacher('cpu')
    candidate=actor_from(cand,'cpu')
    champion=actor_from(champ,'cpu')
    report=run_gate(candidate,champion,teacher.actor,teacher,
                    games=args.games,decisions=args.decisions,seed=472381)
    strict_json_dumps(report,indent=2,sort_keys=True)
    log(f'PASSED: full evaluator + JSON, verdict={report["verdict"]}.')
    log('This tiny sample is ONLY a technical test, NOT proof of improved bot strength.')


if __name__=='__main__':
    main()
