"""Read-only RocketSim 1v1 all-versus-all first-goal evaluator.

Default: 50 games per unordered pair, 25 shared kickoff seeds with roles swapped.
Each game ends with the first goal or a censored timeout after 180 seconds.
No bracket or elimination. Results are saved per game for crash-safe resume.
"""
from __future__ import annotations
import argparse
import csv
import fnmatch
import hashlib
import itertools
import json
import math
import os
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
OUT_DEFAULT = ROOT / 'round_robin_reports'
IGNORE = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
          'round_robin_reports', 'model_tournament_reports'}
TICK_SKIP = 8
FPS = 120
VERSION = 3


def weight_digest(state):
    h=hashlib.sha256()
    for key,tensor in sorted(state.items()):
        if not torch.is_tensor(tensor):raise ValueError('Non-tensor actor state')
        if tensor.is_floating_point() and not torch.isfinite(tensor).all():raise ValueError('Nonfinite actor weights')
        h.update(key.encode());h.update(str((tuple(tensor.shape),tensor.dtype)).encode())
        h.update(tensor.detach().cpu().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def discover(rules, max_mib,all_scripted=False,include=()):
    from chatgpt_ai.policy import policy_shape
    source = ROOT / 'vendor' / 'nexto' / 'nexto-model.pt'
    expected = {k: tuple(v.shape) for k, v in torch.jit.load(str(source), map_location='cpu').state_dict().items()}
    seen, eligible, inventory = {}, [], []
    for i, path in enumerate(sorted(ROOT.rglob('*.pt')), 1):
        if any(part.lower() in IGNORE for part in path.relative_to(ROOT).parts):
            continue
        if include and not any(fnmatch.fnmatchcase(relative(path),pattern) for pattern in include):
            inventory.append({'path':relative(path),'bytes':path.stat().st_size,
                              'kind':'FILTERED','sha256':'','kickoff':'','reason':'Outside --include globs'})
            continue
        mode = 'nexto_v4' if relative(path) == 'vendor/nexto/nexto-model.pt' else 'none'
        for glob, chosen in rules.items():
            if fnmatch.fnmatchcase(relative(path), glob):
                mode = chosen
        if all_scripted:mode='nexto_v4'
        kind, reason, sha = 'UNSUPPORTED', '', ''
        if path.stat().st_size > max_mib * 1024**2:
            kind, reason = 'TOO_LARGE', f'Over {max_mib} MiB'
        else:
            try:
                state=None
                try:
                    loaded=torch.jit.load(str(path),map_location='cpu')
                    shape={k:tuple(v.shape) for k,v in loaded.state_dict().items()}
                    if shape!=expected:raise ValueError('Incompatible TorchScript actor')
                    kind='NEXTO_TS';state=loaded.state_dict()
                except (RuntimeError,ValueError):
                    # Loading third-party weights requires trusted checkpoint files.
                    obj = torch.load(path, map_location='cpu', weights_only=True)
                    if isinstance(obj, dict) and isinstance(obj.get('actor'), dict):
                        shape = {k: tuple(v.shape) for k, v in obj['actor'].items()}
                        if shape == expected:
                            kind = 'NATIVE';state=obj['actor']
                        else:
                            reason = 'Actor architecture incompatible with original Nexto'
                    elif isinstance(obj, dict):
                        try:
                            n_obs, _, n_actions = policy_shape(obj)
                            if (n_obs, n_actions) == (92, 90):
                                kind = 'FF92';state=obj
                            else:
                                reason = f'Unsupported input/action sizes: {n_obs}/{n_actions}'
                        except (ValueError, KeyError, TypeError, AttributeError):
                            reason = 'Unknown .pt state dictionary format'
                    else:
                        reason = 'Unknown .pt content'
            except Exception as exc:
                try:
                    loaded = torch.jit.load(str(path), map_location='cpu')
                    shape = {k: tuple(v.shape) for k, v in loaded.state_dict().items()}
                    if shape == expected:
                        kind = 'NEXTO_TS'
                        state=loaded.state_dict()
                    else:
                        reason = 'TorchScript architecture incompatible with Nexto'
                except Exception:
                    kind = 'UNREADABLE'
                    reason = (type(exc).__name__ + ': ' + str(exc))[:170]
        if kind in ('NEXTO_TS', 'NATIVE', 'FF92'):
            sha = digest(path)
            try:identity = weight_digest(state) + ':' + mode
            except ValueError as exc:kind,reason='UNSUPPORTED',str(exc)
            else:
                if identity in seen:
                    kind, reason = 'DUPLICATE', 'Identical actor weights and kickoff to ' + seen[identity]
                else:
                    seen[identity] = relative(path)
                    eligible.append({'path': relative(path), 'kind': kind, 'sha': sha,
                                     'weight_sha':identity.split(':')[0],
                                     'kickoff': mode, 'id': identity})
        inventory.append({'path': relative(path), 'bytes': path.stat().st_size,
                          'kind': kind, 'sha256': sha, 'kickoff': mode, 'reason': reason})
        if i % 25 == 0:
            print('Scanned', i, 'model files', flush=True)
    return eligible, inventory


def load_bot(bot):
    path = ROOT / bot['path']
    if bot['kind'] == 'NEXTO_TS':
        model = torch.jit.load(str(path), map_location='cpu')
        model.eval()
        return model
    if bot['kind'] == 'NATIVE':
        from auto_league import actor_from
        return actor_from(path, 'cpu')
    if bot['kind'] == 'FF92':
        from chatgpt_ai.policy import LoadedPolicy
        return LoadedPolicy(path)
    raise ValueError('Cannot run ' + bot['kind'])


def action_for(bot, model, agent, nobs, fobs, table):
    if bot['kind'] == 'FF92':
        idx = int(model.act(fobs[agent])[0])
        from rlgym.rocket_league.action_parsers import LookupTableAction
        table=LookupTableAction.make_lookup_table()
    else:
        from auto_league import action_greedy
        idx = action_greedy(model, nobs[agent])
    if not (0 <= idx < len(table)):
        raise ValueError('Model returned invalid action index')
    return table[idx].copy()


def game(a, b, model_a, model_b, seed, a_orange, seconds, engine, teacher, table, script):
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    base = engine.create_base_state()
    FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(base, {})
    KickoffMutator().apply(base, {})
    state = engine.set_state(base, {})
    own = next(cid for cid, car in state.cars.items() if bool(car.is_orange) == a_orange)
    opp = next(cid for cid in state.cars if cid != own)
    player = ((a, model_a, own), (b, model_b, opp))
    from rlgym.rocket_league.action_parsers import LookupTableAction
    ff_builder = None
    if any(bot['kind'] == 'FF92' for bot, _, _ in player):
        from chatgpt_ai.env import make_obs
        ff_builder = make_obs()
        ff_builder.reset(list(state.cars), state, {})
    previous = {}
    touched = False
    for t in range(0, seconds * FPS, TICK_SKIP):
        nobs = {}
        if any(bot['kind'] != 'FF92' for bot, _, _ in player):
            nobs = {v[0]: v for v in teacher.observe(state, previous)}
        fobs = ff_builder.build_obs(list(state.cars), state, {}) if ff_builder else {}
        controls = {cid: action_for(bot, model, cid, nobs, fobs, table)
                    for bot, model, cid in player}
        within = 0
        while within < TICK_SKIP:
            tick = t + within
            # Scripted Nexto acceleration/steering can change within an 8-tick NN block.
            scripted = (tick < len(script) and not touched and
                        any(bot['kickoff'] == 'nexto_v4' for bot, _, _ in player))
            if scripted:
                centered = np.linalg.norm(state.ball.position[:2]) < 1e-6 and state.ball.position[2]<100
                ctrl = {cid: (script[tick] if bot['kickoff'] == 'nexto_v4' and centered
                              else controls[cid]).copy() for bot, _, cid in player}
                state = engine.step({cid: v[None, :] for cid, v in ctrl.items()}, {})
                # Last *applied* action is what the native observer receives.
                previous = ctrl
                touched = touched or any(int(car.ball_touches) > 0 for car in state.cars.values())
                within += 1
            else:
                remaining = TICK_SKIP - within
                state = engine.step({cid: np.tile(v, (remaining, 1))
                                     for cid, v in controls.items()}, {})
                previous = controls
                within = TICK_SKIP
            if bool(state.goal_scored):
                blue_won = float(state.ball.position[1]) > 0
                return 'W1' if blue_won == (not a_orange) else 'W2'
    return 'D'


def schedule(bots, count, seed):
    rng = random.Random(seed)
    seeds = [rng.randrange(1, 2**31) for _ in range(count // 2)]
    for i, j in itertools.combinations(range(len(bots)), 2):
        for s in seeds:
            yield i, j, s, False
            yield i, j, s, True


def standings(bots, records):
    by_id = {b['id']: Counter(W=0, L=0, D=0) for b in bots}
    opponents = {b['id']: set() for b in bots}
    pairs = {}
    for rec in records:
        x, y, out = rec['a'], rec['b'], rec['outcome']
        if out == 'W1':
            by_id[x]['W'] += 1
            by_id[y]['L'] += 1
        elif out == 'W2':
            by_id[x]['L'] += 1
            by_id[y]['W'] += 1
        else:
            by_id[x]['D'] += 1
            by_id[y]['D'] += 1
        opponents[x].add(y)
        opponents[y].add(x)
        pairs.setdefault((x, y), Counter())[out] += 1
    board = []
    for b in bots:
        c = by_id[b['id']]
        n = sum(c.values())
        score = (c['W'] + 0.5 * c['D']) / n if n else 0
        # Descriptive uncertainty; games from a paired seed are correlated.
        board.append({'model': b['path'], 'sha256': b['sha'], 'kind': b['kind'],
                      'kickoff': b['kickoff'], 'games': n,
                      'opponents': len(opponents[b['id']]),
                      'W': c['W'], 'L': c['L'], 'D': c['D'],
                      'score_pct': round(score * 100, 3) if n else ''})
    board.sort(key=lambda v: (v['score_pct'] != '', v['score_pct'] or -1,
                              v['W'] - v['L'], v['model']), reverse=True)
    for rank, row in enumerate(board, 1):
        row['rank'] = rank
    lookup = {b['id']: b['path'] for b in bots}
    head = [{'model1': lookup[x], 'model2': lookup[y], 'W1': c['W1'],
             'W2': c['W2'], 'D': c['D'], 'games': sum(c.values())}
            for (x, y), c in sorted(pairs.items())]
    return board, head


def save_csv(path, rows, headers):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list-only', action='store_true')
    ap.add_argument('--games-per-pair', type=int, default=50)
    ap.add_argument('--seconds', type=int, default=180)
    ap.add_argument('--seed', type=int, default=20261012)
    ap.add_argument('--limit', type=int, default=0, help='Debug only; 0 means all models')
    ap.add_argument('--max-checkpoint-mib', type=int, default=256)
    ap.add_argument('--kickoffs', type=Path, default=ROOT / 'ROUND_ROBIN_KICKOFFS.json')
    ap.add_argument('--report-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--all-scripted-kickoffs',action='store_true',help='Apply the same Nexto kickoff proxy to every compared bot')
    ap.add_argument('--include',action='append',default=[],help='Optional repository-relative model glob; repeat to select finalist folders')
    args = ap.parse_args()
    if args.games_per_pair < 2 or args.games_per_pair % 2:
        ap.error('--games-per-pair must be positive and EVEN (50 recommended)')
    if args.seconds <= 0 or args.max_checkpoint_mib <= 0 or args.limit < 0:
        ap.error('seconds/max size must be >0 and limit >=0')
    out = args.report_dir.resolve()
    if out == ROOT.resolve() or out.is_relative_to((ROOT / 'data').resolve()):
        ap.error('Report directory must be outside data/ and root')
    out.mkdir(parents=True, exist_ok=True)
    rules = json.loads(args.kickoffs.read_text(encoding='utf-8')) if args.kickoffs.exists() else {}
    if not isinstance(rules, dict) or any(v not in ('none', 'nexto_v4') for v in rules.values()):
        ap.error('Kickoff config must be JSON mapping file globs to none or nexto_v4')
    bots, inv = discover(rules, args.max_checkpoint_mib,args.all_scripted_kickoffs,args.include)
    save_csv(out / 'inventory.csv', inv, ['path', 'bytes', 'kind', 'sha256', 'kickoff', 'reason'])
    print('Inventory:', dict(Counter(x['kind'] for x in inv)), flush=True)
    if args.list_only:
        print('Eligible unique bot configurations:', len(bots), flush=True)
        print('Inventory saved at', out / 'inventory.csv')
        return 0
    if args.limit:
        bots = bots[:args.limit]
    if len(bots) < 2:
        print('Not enough compatible models. See inventory.csv.')
        return 2
    # All legitimate models face ALL others: no bracket or early elimination.
    print(f'{len(bots)} models, {len(bots) * (len(bots)-1)//2} matchups, '
          f'{args.games_per_pair} games/matchup, simulated {args.seconds}s/game', flush=True)
    model_hashes = {b['path']: b['sha'] for b in bots}
    from importlib.metadata import version
    protocol={'version':VERSION,'seconds':args.seconds,'seed':args.seed,'kickoffs':rules,
              'all_scripted':args.all_scripted_kickoffs,'engine_rlbot_delay':True,
              'evaluator_sha':digest(Path(__file__)),
              'scheduler_sha':digest(ROOT/'slater_nexto_scheduler_v038b.py'),
              'adapter_shas':{name:digest(ROOT/name) for name in
                  ('nexto_teacher.py','native_nexto.py','auto_league.py','chatgpt_ai/env.py','chatgpt_ai/policy.py',
                   'vendor/nexto/nexto_obs.py','vendor/nexto/original_agent.py')},
              'rlgym_version':version('rlgym-rocket-league'),'rocketsim_version':version('rocketsim'),
              'torch_version':version('torch'),'numpy_version':version('numpy')}
    protocol_sha=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    cache_path = out / 'games.jsonl'
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding='utf-8').splitlines():
            try:
                rec = json.loads(line)
                if rec['outcome'] in ('W1', 'W2', 'D'):
                    cache[rec['key']] = rec
            except (ValueError, KeyError, TypeError):
                pass
    torch.set_num_threads(2)
    from nexto_teacher import NextoTeacher, nexto_actions
    from slater_nexto_scheduler_v038b import KICKOFF
    from rlgym.rocket_league.action_parsers import LookupTableAction
    native_table = nexto_actions()
    ff_table = np.asarray(LookupTableAction.make_lookup_table(), dtype=np.float32)
    if native_table.shape != (90, 8) or ff_table.shape != (90,8):
        raise RuntimeError('Unsupported native or feedforward control table')
    teacher = NextoTeacher('cpu')
    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=True)
    results = []
    active_pair = None
    pair_models = None
    try:
        total = len(bots) * (len(bots)-1) // 2 * args.games_per_pair
        for k, (i, j, seed, orange) in enumerate(schedule(bots, args.games_per_pair, args.seed), 1):
            a, b = bots[i], bots[j]
            pair = (a['id'], b['id'])
            key = json.dumps([protocol_sha, pair, seed, orange], separators=(',', ':'))
            if pair != active_pair:
                for bot in (a, b):
                    if digest(ROOT / bot['path']) != bot['sha']:
                        raise RuntimeError('A model changed while tournament was running: ' + bot['path'])
                active_pair = pair
                pair_models = None
                print(f'[{k}/{total}] {a["path"]}  VS  {b["path"]}', flush=True)
            if key in cache:
                rec = cache[key]
            else:
                if pair_models is None:
                    pair_models = (load_bot(a), load_bot(b))
                outcome = game(a, b, *pair_models, seed, orange, args.seconds,
                               engine, teacher, native_table, KICKOFF)
                rec = {'key': key, 'a': a['id'], 'b': b['id'], 'seed': seed,
                       'a_orange': orange, 'outcome': outcome}
                with cache_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(rec, separators=(',', ':')) + '\n')
                    f.flush();os.fsync(f.fileno())
                cache[key] = rec
            if rec['a'] != a['id'] or rec['b'] != b['id']:
                raise RuntimeError('Cached pairing mismatch')
            results.append(rec)
            if k % 50 == 0 or k == total:
                print(f'Completed {k}/{total} games', flush=True)
    finally:
        engine.close()
    for name, expected in model_hashes.items():
        if digest(ROOT / name) != expected:
            raise RuntimeError('Checkpoint altered during evaluation: ' + name)
    board, head = standings(bots, results)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    save_csv(out / f'leaderboard_{stamp}.csv', board,
             ['rank', 'model', 'sha256', 'kind', 'kickoff', 'games', 'opponents',
              'W', 'L', 'D', 'score_pct'])
    save_csv(out / f'head_to_head_{stamp}.csv', head,
             ['model1', 'model2', 'W1', 'W2', 'D', 'games'])
    report = {'protocol': VERSION, 'created_utc': stamp, 'bots': len(bots),
              'protocol_details':protocol,'protocol_sha256':protocol_sha,
              'games_per_pair': args.games_per_pair, 'simulated_seconds': args.seconds,
              'seed': args.seed, 'definition': 'first goal or censored timeout (D column)',
              'note': 'Nexto v4 kickoff is a RocketSim proxy, not exact RLBot packet timing',
              'leaderboard': board, 'head_to_head': head, 'inventory': inv}
    native=next((row for row in board if row['kind'] in ('NATIVE','NEXTO_TS')),None)
    if native:
        chosen=(ROOT/native['model']).resolve()
        report.update(recommended_source=str(chosen),recommended_source_sha256=digest(chosen),
                      selection_status='ROUND_ROBIN_SCREEN_NOT_FULL_MATCH_VERIFIED')
    (out / f'results_{stamp}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for row in board:
        print(f'#{row["rank"]} {row["model"]}: W{row["W"]} L{row["L"]} D{row["D"]}, score={row["score_pct"]}%', flush=True)
    print('REPORTS:', out, flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted: games.jsonl contains all finished games. Restart to resume.', flush=True)
        raise SystemExit(130)
