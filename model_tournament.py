"""Read-only, resumable tournament for NATIVE Nexto-architecture checkpoints.

Uses the existing project's RocketSim / AutoLeague first-goal evaluator.
Does not train, promote, copy, delete or overwrite model weights.
No attempts to load legacy 92-feature PPO / student models as Nexto actors.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import torch

from auto_league import ROOT, SOURCE_MODEL, DATA, actor_from, duel, sha256, strict_json_dumps
from independent_nexto_benchmark import build_cases
from nexto_teacher import NextoTeacher

VERSION = 1
REPORT_DIR = ROOT / 'model_tournament_reports'


def say(message):
    print(message, flush=True)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def candidate_paths(root: Path):
    data = root / 'data'
    if not data.exists():
        raise FileNotFoundError(f'Expected local training folder: {data}')
    paths = list(data.rglob('*.pt'))
    # The original Nexto TorchScript is the standard opponent, not a trained candidate.
    def priority(p):
        rel = p.relative_to(data).as_posix().lower()
        if rel == 'autoleague/champion.pt': return (0, rel)
        if rel == 'autoleague/candidate.pt': return (1, rel)
        if rel == 'native_nexto/best_10k.pt': return (2, rel)
        if rel.startswith('autoleague/backups/'): return (3, rel)
        if rel.startswith('autoleague/'): return (4, rel)
        return (5, rel)
    return sorted(paths, key=priority)


def actor_spec():
    model = torch.jit.load(str(SOURCE_MODEL), map_location='cpu')
    return {k: tuple(v.shape) for k, v in model.state_dict().items()}


def classify_file(path: Path, expected: dict):
    try:
        obj = torch.load(path, map_location='cpu', weights_only=True)
        if not isinstance(obj, dict) or not isinstance(obj.get('actor'), dict):
            return 'OTHER_FORMAT', 'No native Nexto actor state_dict'
        actual = {k: tuple(v.shape) for k, v in obj['actor'].items()}
        if actual != expected:
            return 'OTHER_ARCHITECTURE', 'Actor weights do not match original Nexto architecture'
        return 'NATIVE', ''
    except Exception as exc:
        return 'UNREADABLE', f'{type(exc).__name__}: {str(exc)[:160]}'


def inventory(root: Path, max_mib: int):
    expected = actor_spec()
    records = []
    unique = {}
    for i, p in enumerate(candidate_paths(root), 1):
        size = p.stat().st_size
        record = {'path': _rel(p), 'bytes': size, 'kind': '', 'sha256': '', 'duplicate_of': '', 'reason': ''}
        if size > max_mib * 1024 * 1024:
            record.update(kind='TOO_LARGE', reason=f'Above {max_mib} MiB per-checkpoint scan limit')
        else:
            kind, why = classify_file(p, expected)
            record.update(kind=kind, reason=why)
            if kind == 'NATIVE':
                digest = sha256(p)
                record['sha256'] = digest
                if digest in unique:
                    record['kind'] = 'DUPLICATE'
                    record['duplicate_of'] = _rel(unique[digest])
                else:
                    unique[digest] = p
        records.append(record)
        if i % 25 == 0:
            say(f'  Inventory: examined {i} files...')
    return records, unique


def write_inventory(records: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        cols = ['path', 'bytes', 'kind', 'sha256', 'duplicate_of', 'reason']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(records)


def load_cache(path):
    data = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict) and 'key' in item and 'result' in item:
                    data[item['key']] = item['result']
            except (json.JSONDecodeError, ValueError):
                pass  # Only complete, valid lines can be reused.
    return data


def cache_key(a, b, seed, pairs, decisions):
    return json.dumps([VERSION, a, b, int(seed), int(pairs), int(decisions)], separators=(',', ':'))


def save_cache(path, key, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(strict_json_dumps({'key': key, 'result': result}, separators=(',', ':')) + '\n')
        f.flush()


def score(result):
    return float(result['score'])


def sha_check(path, digest):
    if not path.exists() or sha256(path) != digest:
        raise RuntimeError(f'CHECKPOINT CHANGED: {_rel(path)}; stop training and rerun safely.')


def baseline_safety(data_dir):
    champion = data_dir / 'champion.pt'
    statepath = data_dir / 'league_state.json'
    if champion.exists() and statepath.exists():
        state = json.loads(statepath.read_text(encoding='utf-8'))
        digest = sha256(champion)
        if digest != state.get('champion_sha'):
            raise RuntimeError('Champion hash does not match league_state.json. Refusing tournament.')
        if state.get('phase') != 'train':
            raise RuntimeError('AutoLeague is in a pending non-train phase. Resolve it first.')
        return champion, digest
    if champion.exists() != statepath.exists():
        raise RuntimeError('Champion or league_state.json missing; AutoLeague state may be incomplete.')
    return None, None


def results_table(ranked, results):
    lines = ['rank | score | W-L-D | SHA | model']
    for n, digest in enumerate(ranked, 1):
        r = results[digest]
        wins = r['outcomes'].get('ours', 0); losses = r['outcomes'].get('nexto', 0)
        draws = r['outcomes'].get('draw', 0)
        lines.append(f'{n:>4} | {score(r):.3f} | {wins}-{losses}-{draws} | {digest[:12]} | {_rel(r["_path"])}')
    return '\n'.join(lines)


def rank_by_score(records):
    return sorted(records, key=lambda d: (float(records[d]['score']), records[d]['outcomes'].get('ours',0) - records[d]['outcomes'].get('nexto',0), d), reverse=True)


def anchored_selection(ranked, n, champion_sha):
    chosen = ranked[:n]
    if champion_sha in ranked and champion_sha not in chosen and n > 0:
        chosen[-1] = champion_sha
    return chosen


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--list-only', action='store_true', help='Inventory only, no simulations')
    p.add_argument('--thorough', action='store_true', help='More matches, substantially slower')
    p.add_argument('--limit', type=int, default=0, help='Optional cap on unique native checkpoints (0 = ALL)')
    p.add_argument('--max-checkpoint-mib', type=int, default=256)
    p.add_argument('--semifinalists', type=int, default=8)
    p.add_argument('--finalists', type=int, default=4)
    p.add_argument('--seed', type=int, default=150982731)
    p.add_argument('--decisions', type=int, default=750)
    p.add_argument('--screen-pairs', type=int, default=None)
    p.add_argument('--semi-pairs', type=int, default=None)
    p.add_argument('--final-pairs', type=int, default=None)
    p.add_argument('--h2h-pairs', type=int, default=None)
    args = p.parse_args(argv)
    if args.limit < 0 or args.max_checkpoint_mib <= 0 or args.semifinalists < 1 or not 2 <= args.finalists <= 4 or args.decisions <= 0:
        p.error('Invalid positive counts (finalists must be 2, 3, or 4).')
    counts = (20,60,180,100) if args.thorough else (8,24,80,40)
    screen_pairs = counts[0] if args.screen_pairs is None else args.screen_pairs
    semi_pairs = counts[1] if args.semi_pairs is None else args.semi_pairs
    final_pairs = counts[2] if args.final_pairs is None else args.final_pairs
    h2h_pairs = counts[3] if args.h2h_pairs is None else args.h2h_pairs
    if min(screen_pairs,semi_pairs,final_pairs,h2h_pairs) <= 0:
        p.error('Every pair count must be > 0')
    root = ROOT
    out = REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    say('READ-ONLY MODEL TOURNAMENT. No changes to champion, candidate or league state.')
    say('Scanning training model files from ' + str(root/'data'))
    champion_path, champion_sha = baseline_safety(DATA)
    records, unique = inventory(root, args.max_checkpoint_mib)
    write_inventory(records, out / 'inventory.csv')
    count = defaultdict(int)
    for entry in records: count[entry['kind']] += 1
    say('Inventory: ' + str(dict(count)))
    say('Inventory saved: ' + str(out/'inventory.csv'))
    if args.list_only:
        for digest, path in unique.items(): say(f'  NATIVE {digest[:12]} {_rel(path)}')
        say('No simulation performed. OTHER_FORMAT / OTHER_ARCHITECTURE models need separate adapters.')
        return 0
    if len(unique) < 2:
        say('Not enough compatible unique native checkpoints for a tournament; check inventory.csv')
        return 2
    ordered = list(unique.items())
    if args.limit:
        ordered = ordered[:args.limit]
        if champion_sha in unique and champion_sha not in dict(ordered):
            ordered[-1] = (champion_sha, unique[champion_sha])
    unique = dict(ordered)
    if len(unique) < 2:
        say('Need at least 2 unique native checkpoints.'); return 2
    torch.set_num_threads(2)
    teacher = NextoTeacher('cpu')
    nexto = teacher.actor
    nexto_sha = sha256(SOURCE_MODEL)
    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=False)
    cache_file = out / 'eval_cache.jsonl'
    cache = load_cache(cache_file)
    seed = args.seed
    def versus(first_sha, first_actor, second_sha, second_actor, pairs, this_seed, label):
        key = cache_key(first_sha, second_sha, this_seed, pairs, args.decisions)
        if key in cache:
            say('  CACHE ' + label)
            return cache[key]
        result = duel(first_actor, second_actor, teacher, engine, build_cases(this_seed, pairs), args.decisions, label=label)
        cache[key] = result
        save_cache(cache_file, key, result)
        return result
    def do_stage(stage_name, shas, pairs, this_seed):
        results={}
        for i, digest in enumerate(shas, 1):
            path = unique[digest]
            sha_check(path, digest)
            say(f'[{stage_name} {i}/{len(shas)}] {_rel(path)} | SHA {digest[:12]}')
            actor = actor_from(path, 'cpu')
            r=versus(digest,actor,nexto_sha,nexto,pairs,this_seed,f'{stage_name} {digest[:12]} vs Nexto')
            r=dict(r); r['_path']=path
            results[digest]=r
        ranked = rank_by_score(results)
        say('\n' + stage_name + ' standings:\n' + results_table(ranked, results) + '\n')
        return results,ranked
    try:
        screen, r_screen = do_stage('SCREEN', list(unique), screen_pairs,seed+11)
        semifinalists = anchored_selection(r_screen,min(args.semifinalists,len(r_screen)),champion_sha)
        semi,r_semi=do_stage('SEMIFINAL',semifinalists,semi_pairs,seed+200011)
        finalists=anchored_selection(r_semi,min(args.finalists,len(r_semi)),champion_sha)
        final,r_final=do_stage('FINAL',finalists,final_pairs,seed+400013)
        pairwise = []
        h2h_wins=defaultdict(list)
        for i, a_sha in enumerate(finalists):
            for b_sha in finalists[i+1:]:
                sha_check(unique[a_sha], a_sha);sha_check(unique[b_sha],b_sha)
                say(f'[HEAD TO HEAD] {_rel(unique[a_sha])} vs {_rel(unique[b_sha])}')
                r = versus(a_sha,actor_from(unique[a_sha],'cpu'),b_sha,actor_from(unique[b_sha],'cpu'),h2h_pairs,seed+600019,
                           f'{a_sha[:10]} vs {b_sha[:10]}')
                pairwise.append({'a':a_sha,'b':b_sha,'a_vs_b':r})
                h2h_wins[a_sha].append(score(r));h2h_wins[b_sha].append(1-score(r))
        # A repeated seeded Nexto-vs-Nexto control estimates possible side/scenario bias.
        control = versus(nexto_sha,nexto,nexto_sha,nexto,20,seed+800021,'Nexto vs itself control')
    finally:
        engine.close()
    if champion_path:
        sha_check(champion_path, champion_sha)
    for digest in finalists:
        sha_check(unique[digest],digest)
    final_rank = sorted(finalists,key=lambda d:(0.65*score(final[d])+0.35*(sum(h2h_wins[d])/len(h2h_wins[d])),score(final[d])),reverse=True)
    overview=[]
    for digest in final_rank:
        h2h_avg = sum(h2h_wins[digest])/len(h2h_wins[digest])
        overview.append({'rank':len(overview)+1,'sha256':digest,'model':_rel(unique[digest]),
                         'score_vs_nexto':score(final[digest]),'score_vs_finalists':h2h_avg,
                         'combined_heuristic':0.65*score(final[digest])+0.35*h2h_avg,
                         'outcomes_vs_nexto':final[digest]['outcomes']})
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report={'kind':'read_only_native_nexto_tournament_v1','created_utc':stamp,
            'evaluation_note':'FIRST-GOAL / decision-cap ONLY, not full five-minute matches. Short screens cause selection noise. No automatic promotions.',
            'scenario_protocol':'paired seeds and opposite team sides, greedy action policies',
            'pairs':{'screen':screen_pairs,'semifinal':semi_pairs,'final':final_pairs,'head_to_head':h2h_pairs},
            'seed':seed,'decisions_per_episode_cap':args.decisions,'inventory_summary':dict(count),
            'unique_native_models':len(unique),'champion_sha256_at_start':champion_sha,
            'screen':[{'sha256':d,'model':_rel(unique[d]),'result':{k:v for k,v in screen[d].items() if k!='_path'}} for d in r_screen],
            'semifinal':[{'sha256':d,'model':_rel(unique[d]),'result':{k:v for k,v in semi[d].items() if k!='_path'}} for d in r_semi],
            'final':[{'sha256':d,'model':_rel(unique[d]),'result':{k:v for k,v in final[d].items() if k!='_path'}} for d in r_final],
            'head_to_head':pairwise,'nexto_self_control':control,'final_standings':overview}
    path=out/f'tournament_{stamp}.json'
    path.write_text(strict_json_dumps(report,indent=2)+'\n',encoding='utf-8')
    with (out/f'tournament_{stamp}_leaderboard.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['rank','model','sha256','score_vs_nexto','score_vs_finalists','combined_heuristic','outcomes_vs_nexto'])
        w.writeheader();w.writerows([{**r,'outcomes_vs_nexto':str(r['outcomes_vs_nexto'])} for r in overview])
    say('\nFINAL STANDINGS (HEURISTIC, not definitive):')
    for row in overview:
        say(f'#{row["rank"]}: Nexto={row["score_vs_nexto"]:.3f}, H2H={row["score_vs_finalists"]:.3f}, '
            f'SHA={row["sha256"][:12]}, {_rel(unique[row["sha256"]])}')
    say('Report: ' + str(path))
    say('Champion and every checkpoint left UNCHANGED. No promotion was performed.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say('Interrupted. No checkpoint modifications. Completed evaluations cached for re-run.')
        sys.exit(130)
    except Exception as exc:
        say(f'ERROR: {type(exc).__name__}: {exc}')
        raise
