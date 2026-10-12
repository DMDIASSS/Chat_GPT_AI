"""Slater v0.2.8: held-out, read-only, paired FIRST-GOAL 1v1 Nexto evaluation.

Compare frozen original Cycle9 with one or more v027 checkpoints on NEW kickoff seeds.
Reseeds Python AND NumPy RNG before every game and verifies replay determinism.
No optimizer, no training, no checkpoint promotion. Does NOT approximate full 5-min games.

Smoke:
 .venv\\Scripts\\python.exe slater_nexto_heldout_eval_v028.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 4 --max-episode-steps 120 --out data/isolated/nexto_heldout_v028_smoke.json
Held-out:
 .venv\\Scripts\\python.exe slater_nexto_heldout_eval_v028.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 24 --max-episode-steps 450 --out data/isolated/nexto_heldout_v028_u60_24.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired

NEXTOSHA = paired.EXPECTED_NEXTO_SHA256


def checked_candidate(file: str, root: Path, expected_source: str, expected_nexto: str):
    path = Path(file).resolve()
    isolated = (root / 'data' / 'isolated').resolve()
    if not path.is_relative_to(isolated) or path.suffix != '.pt' or not path.is_file():
        raise ValueError('Only existing .pt checkpoints under data/isolated can be evaluated')
    doc = torch.load(path, map_location='cpu', weights_only=True)
    if (not isinstance(doc, dict) or doc.get('stage') != 'slater_v027' or
            doc.get('source_sha') != expected_source or
            not isinstance(doc.get('actor'), dict) or
            not isinstance(doc.get('global_updates'), int)):
        raise ValueError('Candidate is not a source-verified v027 PPO checkpoint')
    meta = doc.get('meta', {})
    if meta and meta.get('nexto_sha') != expected_nexto:
        raise ValueError('Checkpoint Nexto source checksum mismatch')
    return path, doc


def kickoff_signature(env):
    """Fingerprints starting physical state rather than trusting seed labels."""
    st = env.state
    floats = []
    for item in (st.ball, st.cars['blue-0'].physics, st.cars['orange-0'].physics):
        for attr in ('position', 'linear_velocity', 'angular_velocity', 'forward'):
            if hasattr(item, attr):
                floats.extend(np.asarray(getattr(item, attr), dtype=np.float64).flatten().tolist())
    for side in ('blue-0', 'orange-0'):
        floats.append(float(st.cars[side].boost_amount))
    # Strict enough to detect different kickoffs, tolerant of float materialization noise.
    value = np.asarray(np.round(floats, 5), dtype='<f8')
    return hashlib.sha256(value.tobytes()).hexdigest()[:20]


def deterministic_game(env, actor, seed: int, side: str):
    """Explicitly seed both main RNGs. Evaluate greedily and read only."""
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    obs = env.reset(seed)
    signature = kickoff_signature(env)
    while True:
        action = paired.greedy_action(actor, obs, env.device)
        obs, _, done, info = env.step(action)
        if done:
            return {
                'seed': seed, 'side': side, 'kickoff_signature': signature,
                'outcome': int(info['outcome']),
                'touches': int(info['student_touches']),
                'opponent_touches': int(info['opponent_touches']),
                'steps': int(info['steps']),
                'final_ball_progress_uu': round(float(info['ball_y']) * (1 if side == 'blue' else -1), 3),
            }


def check_same_game(a, b):
    return all(a[k] == b[k] for k in ('seed','side','kickoff_signature','outcome',
                                     'touches','opponent_touches','steps','final_ball_progress_uu'))


def run_evaluation(actors, nexto, actions, observer, seeds, horizon, root_seed):
    blue = base.Native1v1(actions, observer, nexto, max_steps=horizon, device='cpu')
    orange = paired.RoleSwap1v1(actions, observer, nexto, max_steps=horizon, device='cpu')
    records = []
    baseline_probes = {}
    try:
        # First verify game reproducibility; do not trust paired confidence intervals if it fails.
        for side, env in (('blue', blue), ('orange', orange)):
            first = deterministic_game(env, actors['original'], root_seed, side)
            repeat = deterministic_game(env, actors['original'], root_seed, side)
            baseline_probes[side] = first
            if not check_same_game(first, repeat):
                raise RuntimeError('NONDETERMINISTIC_BASELINE ' + json.dumps({'first':first,'repeat':repeat}) +
                    '. Stop: this simulator/observer must be made reproducible before comparing policies.')
        print('DETERMINISM_CHECK PASS: original Cycle9 repeated identically as Blue and Orange', flush=True)
        for i in range(seeds):
            seed = root_seed + 997 * i
            for side, env in (('blue', blue), ('orange', orange)):
                baseline_sig = None
                for name, actor in actors.items():
                    row = deterministic_game(env, actor, seed, side)
                    if baseline_sig is None:
                        baseline_sig = row['kickoff_signature']
                    elif row['kickoff_signature'] != baseline_sig:
                        raise RuntimeError(f'Start state differs for {name}, seed={seed}, side={side}')
                    row['policy'] = name
                    records.append(row)
            if (i+1) % 8 == 0 or i+1 == seeds:
                print('PROGRESS', i+1, '/', seeds, 'held-out kickoff seeds', flush=True)
        # Detect simulator/observer drift over the whole evaluation, not just consecutive resets.
        for side, env in (('blue', blue), ('orange', orange)):
            last = deterministic_game(env, actors['original'], root_seed, side)
            if not check_same_game(baseline_probes[side], last):
                raise RuntimeError('NONDETERMINISTIC_BASELINE_AFTER_EVAL: original result changed across evaluation')
        print('END_DETERMINISM_CHECK PASS', flush=True)
    finally:
        blue.close()
        orange.close()
    summaries = {name: paired.aggregate([r for r in records if r['policy']==name]) for name in actors}
    comparisons={}
    for name in actors:
        if name == 'original':
            continue
        pair_records = [dict(r, policy='candidate' if r['policy']==name else 'original')
                        for r in records if r['policy'] in (name, 'original')]
        comparisons[name] = paired.comparison(pair_records)
    by_side = {name: {side:paired.aggregate([r for r in records if r['policy']==name and r['side']==side])
                      for side in ('blue','orange')} for name in actors}
    return {'summaries':summaries, 'paired_vs_original':comparisons, 'by_side':by_side, 'records':records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True, help='Primary v027 candidate, recommend u60')
    parser.add_argument('--extra', action='append', default=[], help='Optional secondary v027 candidate(s)')
    parser.add_argument('--seeds', type=int, default=24)
    parser.add_argument('--seed', type=int, default=1700420699, help='New held-out seed base')
    parser.add_argument('--max-episode-steps', type=int, default=450)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if not (4 <= args.seeds <= 256 and 60 <= args.max_episode_steps <= 1800 and
            1 <= args.seed < 2**31 and len(args.extra) <= 3):
        parser.error('Invalid limits: seeds 4-256, steps 60-1800, extras <=3')
    root=Path.cwd().resolve()
    out=base.check_output(args.out, root, '.json')
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA, cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    source=root / CYCLE9
    nexto_file=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_file)!=NEXTOSHA:
        raise RuntimeError('Cycle9/Nexto checksum guard failed')
    paths=[args.checkpoint]+args.extra
    loaded=[checked_candidate(p,root,CYCLE9_SHA,NEXTOSHA) for p in paths]
    if len(set(str(p) for p,d in loaded)) != len(loaded):
        raise ValueError('Duplicate candidate path')
    teacher, _ = cycle9_pair(root)
    teacher.eval()
    actors={'original':teacher}
    checkpoint_info={}
    for file, doc in loaded:
        actor, _ = cycle9_pair(root)
        actor.load_state_dict(doc['actor'],strict=True)
        actor.eval()
        label=f"u{doc['global_updates']:04d}"
        if label in actors:
            raise ValueError('Two checkpoints have identical update IDs')
        actors[label]=actor
        checkpoint_info[label]={'file':str(file),'sha256':base.sha256(file),
                                'global_updates':doc['global_updates']}
    for actor in actors.values():
        for p in actor.parameters():
            p.requires_grad_(False)
    opponent=torch.jit.load(str(nexto_file), map_location='cpu')
    opponent.eval()
    for p in opponent.parameters():
        p.requires_grad_(False)
    torch.set_num_threads(2)
    lookup=nexto_actions()
    actions=np.stack([np.asarray(lookup[i],dtype=np.float32).reshape(8) for i in range(90)])
    if actions.shape!=(90,8): raise RuntimeError('Wrong Nexto action table')
    print('HELDOUT_REAL_NEXTO_FIRST_GOAL: read-only, greedy, Blue+Orange', flush=True)
    print('POLICIES',list(actors),'SEEDS',args.seeds,'MAX_STEPS',args.max_episode_steps, 'SEED_BASE',args.seed, flush=True)
    print('SOURCE_CHECKSUMS', CYCLE9_SHA, NEXTOSHA, flush=True)
    started=time.perf_counter()
    output=run_evaluation(actors, opponent, actions, TeamObserver(), args.seeds, args.max_episode_steps, args.seed)
    report={'schema_version':1,'purpose':'held-out short first-goal vs frozen Nexto (NOT full match)',
            'seed_base':args.seed,'seeds':args.seeds,'sides':2,'max_episode_steps':args.max_episode_steps,
            'source_cycle9_sha':CYCLE9_SHA,'source_nexto_sha':NEXTOSHA,
            'checkpoints':checkpoint_info,'elapsed_seconds':round(time.perf_counter()-started,3),**output}
    print('OVERALL',json.dumps(output['summaries'],sort_keys=True),flush=True)
    print('PAIRED_VS_ORIGINAL',json.dumps(output['paired_vs_original'],sort_keys=True),flush=True)
    print('BY_SIDE',json.dumps(output['by_side'],sort_keys=True),flush=True)
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_file)!=NEXTOSHA:
        raise RuntimeError('Original checkpoint checksums changed, aborting report')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf8') as f:
        json.dump(report,f,indent=2,sort_keys=True)
    print('SAVED_READ_ONLY',out,'NO_TRAINING_NO_PROMOTION_SOURCE_CHECKSUMS_UNCHANGED',flush=True)

if __name__=='__main__':
    main()
