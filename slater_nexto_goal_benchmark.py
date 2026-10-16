"""Nexto-only fixed-budget first-goal rounds; source-preserving, resumable descriptive benchmark."""
from copy import deepcopy
import json
import math
from pathlib import Path
import time

DEFAULT_GOALS = {'rounds_per_format': 40, 'timeout_seconds': 90,
                 'early_stop_streak': 10, 'seed_base': 881000000,
                 'formats': ['1v1', '2v2', '3v3']}


def validate_goal_config(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_GOALS):
        raise ValueError('Unknown goal benchmark settings')
    cfg = {**deepcopy(DEFAULT_GOALS), **deepcopy(value)}
    for key, low, high in [('rounds_per_format', 30, 50), ('early_stop_streak', 8, 12),
                           ('seed_base', 0, 2000000000)]:
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    if cfg['rounds_per_format'] % 2:
        raise ValueError('Round budget must be even: colors are evaluated in pairs')
    if (type(cfg['timeout_seconds']) not in (int, float)
            or not math.isfinite(cfg['timeout_seconds']) or not .1 <= cfg['timeout_seconds'] <= 300):
        raise ValueError('Timeout must be finite, between .1 and 300 seconds')
    cfg['timeout_seconds'] = round(cfg['timeout_seconds'] * 120) / 120
    if cfg['formats'] != ['1v1', '2v2', '3v3']:
        raise ValueError('This benchmark tests exactly 1v1, 2v2 and 3v3')
    return cfg


def totals(records, cfg, *, early_stop=True):
    records = sorted(records, key=lambda r: (r['seed'], r['learner_team'] == 'orange'))
    wins = sum(r['goals_for'] == 1 for r in records)
    losses = sum(r['goals_against'] == 1 for r in records)
    draws = len(records) - wins - losses
    goals = wins + losses
    outcomes = ['WIN' if r['goals_for'] else 'LOSS' if r['goals_against'] else 'DRAW' for r in records]
    streak = 0
    if outcomes:
        for outcome in reversed(outcomes):
            if outcome != outcomes[-1]:
                break
            streak += 1
    status = 'ROUND_BUDGET_COMPLETE' if len(records) >= cfg['rounds_per_format'] else 'EVALUATING'
    assignment = None
    # Check only after a complete color pair so an early result cannot favor a color.
    if early_stop and len(records) % 2 == 0 and streak >= cfg['early_stop_streak']:
        assignment = outcomes[-1]
        status = 'AUTO_' + assignment + '_STREAK'
    assigned_rate = 1.0 if assignment == 'WIN' else 0.0 if assignment == 'LOSS' else None
    return {'rounds': len(records), 'wins': wins, 'draws': draws, 'losses': losses,
            'goals_for': wins, 'goals_against': losses, 'combined_goals': goals,
            'win_rate': wins / len(records) if records else None,
            'observed_win_rate': wins / len(records) if records else None,
            'assigned_win_rate': assigned_rate, 'assigned_result': assignment,
            'auto_assigned': assignment is not None, 'last_streak': streak,
            'decisive_win_rate': wins / goals if goals else None,
            'draw_rate': draws / len(records) if records else None,
            'points_rate': (wins + .5 * draws) / len(records) if records else None,
            'simulated_seconds': sum(r['seconds'] for r in records), 'status': status,
            'full_budget_met': len(records) >= cfg['rounds_per_format']}


def make_job(protocol, candidate, rival, mode, pair_index, side):
    import slater_model_selection as s
    cfg = protocol['settings']['goal_race']
    size = int(mode[0])
    seed = cfg['seed_base'] + (size - 1) * 1000000 + pair_index * 997
    job = s.game_descriptor(protocol, candidate, rival, candidate, [size, size],
                            seed, side, cfg['timeout_seconds'], 'candidate_squad')
    job.pop('id')
    job['stop_after_first_goal'] = True
    job['id'] = s.canonical_hash({'round': job, 'protocol_sha': protocol['protocol_sha']})
    return job


def wave_paths(folder):
    return sorted(p for p in folder.glob('wave_*.json') if not p.name.endswith('.hashes.json'))


def source_label(source):
    """Show native checkpoint IDs instead of the shared actor.pt basename."""
    path = Path(source['path'])
    if path.name == 'actor.pt' and path.parent.name.startswith('checkpoint_'):
        return path.parent.name
    return path.name


def load_ledger(run):
    import slater_model_selection as s
    jobs, records = {}, {}
    for wave in wave_paths(run / 'goal_rounds'):
        rows = s.read_json(wave)['jobs']
        receipt = s.read_json(wave.with_suffix('.hashes.json'), {})
        for job in rows:
            if job['id'] in jobs:
                raise ValueError('Duplicate round in benchmark ledger')
            jobs[job['id']] = job
            path = run / 'cache/records' / (job['id'] + '.json')
            if not path.is_file():
                if job['id'] in receipt:
                    raise ValueError('Committed benchmark round is missing')
                continue
            if job['id'] in receipt and s.sha256(path) != receipt[job['id']]:
                raise ValueError('Committed benchmark round changed')
            records[job['id']] = s.validate_record(job, s.read_json(path))
    return jobs, records


def summarize(run, protocol, inventory, records, status=None):
    import slater_model_selection as s
    cfg = protocol['settings']['goal_race']
    grouped = {}
    for row in records.values():
        mode = f"{row['format'][0]}v{row['format'][1]}"
        grouped.setdefault((row['candidate_id'], mode), []).append(row)
    rows = []
    for candidate in inventory['candidate_ids']:
        model = inventory['models'][candidate]
        aliases = sorted({source_label(src) for src in model['source_paths'] if src['families']})
        modes = {}
        for mode in cfg['formats']:
            rounds = grouped.get((candidate, mode), [])
            modes[mode] = {**totals(rounds, cfg), 'colors': {
                color: totals([r for r in rounds if r['learner_team'] == color], cfg, early_stop=False)
                for color in ('blue', 'orange')}}
        rates = [m['win_rate'] for m in modes.values()]
        complete = all(m['status'] != 'EVALUATING' for m in modes.values())
        rows.append({'id': candidate, 'sources': aliases, 'source_paths': model['source_paths'],
                     'formats': modes, 'complete': complete,
                     'balanced_win_rate': sum(rates) / 3 if all(r is not None for r in rates) else None})
    complete = all(row['complete'] for row in rows)
    doc = {'status': status or ('GOAL_BENCHMARK_COMPLETE' if complete else 'EVALUATING'),
           'phase': 'goal_benchmark', 'complete': complete, 'completed_games': len(records),
           'completed_model_formats': sum(m['status'] != 'EVALUATING' for r in rows for m in r['formats'].values()),
           'total_model_formats': len(rows) * 3, 'settings': cfg, 'models': rows,
           'protocol_sha': protocol['protocol_sha'], 'confirmed_best': False,
           'all_sources_preserved': True, 'auto_promotion': False,
           'win_rate_definition': 'wins / (wins + draws + losses); first-goal rounds, not regulation matches',
           'note': 'Streak-based early stopping gives assigned results, not measured probabilities or guarantees. '
                   'Observed win rate is kept separately. Each format stops independently; colors finish in pairs.'}
    s.atomic_json(run / 'goal_benchmark.json', doc)
    s.atomic_json(run / 'progress.json', {k: doc[k] for k in ('status', 'phase', 'complete', 'completed_games',
                                                           'completed_model_formats', 'total_model_formats')})
    lines = ['# Nexto goal-round benchmark', '',
             f"Status: {doc['status']}; {len(records)} rounds; budget {cfg['rounds_per_format']} rounds per model per format.",
             '', 'Top 20 per format below; all checkpoints and per-color results are in goal_benchmark.json and winrates.csv.', 'Win rate = wins / all rounds. Decisive win rate excludes draws.',
             'These are first-goal rounds with a no-goal timeout, not five-minute match win rates.',
             f"Auto assignment: {cfg['early_stop_streak']} consecutive identical outcomes, checked after both colors.", 'AUTO results are heuristic assignments; observed win rate and real W/D/L remain separate.', '']
    for mode in cfg['formats']:
        lines += [f'## {mode}', '', '| Rank | Checkpoint | Observed win rate | Assigned result | W / D / L | Goals | Status |',
                  '| --- | --- | ---: | ---: | --- | --- | --- |']
        ranked = sorted(rows, key=lambda r: (r['formats'][mode]['status'] == 'EVALUATING',
                    -(r['formats'][mode]['assigned_win_rate'] if r['formats'][mode]['assigned_win_rate'] is not None else r['formats'][mode]['win_rate'] or 0), -(r['formats'][mode]['points_rate'] or 0), r['id']))
        for i, row in enumerate(ranked[:20], 1):
            m = row['formats'][mode]
            pct = lambda v: '—' if v is None else f'{100*v:.1f}%'
            lines.append(f"| {i} | {', '.join(row['sources'])} | {pct(m['win_rate'])} | "
                         f"{('AUTO DRAW' if m['assigned_result'] == 'DRAW' else 'AUTO ' + pct(m['assigned_win_rate']) if m['auto_assigned'] else '—')} | {m['wins']} / {m['draws']} / {m['losses']} | "
                         f"{m['goals_for']}:{m['goals_against']} | {m['status']} |")
        lines.append('')
    temporary = run / 'SHORTLIST.md.writing'
    temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temporary.replace(run / 'SHORTLIST.md')
    import csv
    csv_path = run / 'winrates.csv.writing'
    with csv_path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['checkpoint', 'format', 'rounds', 'wins', 'draws', 'losses',
                         'observed_win_rate_percent', 'assigned_win_rate_percent',
                         'assigned_result', 'status', 'goals_for', 'goals_against'])
        for row in rows:
            for mode, m in row['formats'].items():
                percent = lambda x: '' if x is None else round(x * 100, 3)
                writer.writerow([', '.join(row['sources']), mode, m['rounds'], m['wins'], m['draws'], m['losses'],
                    percent(m['win_rate']), percent(m['assigned_win_rate']), m['assigned_result'] or '',
                    m['status'], m['goals_for'], m['goals_against']])
    csv_path.replace(run / 'winrates.csv')
    return doc


def rebuild_report(run, build_dir=None):
    import slater_model_selection as s
    protocol = s.read_json(run / 'protocol.json')
    inventory = s.verify_run(run, protocol, build_dir)
    _, records = load_ledger(run)
    return summarize(run, protocol, inventory, records)


def execute_wave(run, protocol, inventory, jobs, wave_path, build_dir=None):
    import slater_model_selection as s
    # Include one baseline round to satisfy the existing evaluator manifest contract;
    # after its first execution this is cached and costs no extra simulation.
    baseline = make_job(protocol, inventory['roles']['baseline'], inventory['roles']['rival:nexto'], '1v1', 0, 'blue')
    group = {job['id']: job for job in [baseline, *jobs]}
    folder = run / 'goal_native' / s.canonical_hash(sorted(group))[:20]
    folder.mkdir(parents=True, exist_ok=True)
    s.atomic_json(folder / 'manifest.json', s.native_manifest(run, protocol, inventory, list(group.values())))
    command = [s.native.binary_path(build_dir), '--mode', 'selector-eval', '--eval-manifest',
               folder / 'manifest.json', '--out', folder, '--meshes', s.native.helper.meshes(),
               '--device', protocol['settings']['device'], '--pause', run / 'PAUSE',
               '--eval-worlds', protocol['settings']['worlds']]
    s.native.checked_process(command, folder / f'eval_{time.time_ns()}.log',
                             marker='SLATER_SELECTOR_COMPLETE', pause=run / 'PAUSE')
    receipt_path = wave_path.with_suffix('.hashes.json')
    receipt = s.read_json(receipt_path, {})
    found = {}
    for job in jobs:
        path = run / 'cache/records' / (job['id'] + '.json')
        if path.is_file():
            row = s.validate_record(job, s.read_json(path))
            digest = s.sha256(path)
            if job['id'] in receipt and receipt[job['id']] != digest:
                raise ValueError('Committed benchmark round changed')
            receipt[job['id']] = digest
            found[job['id']] = row
    s.atomic_json(receipt_path, receipt)
    return found


def run_benchmark(name, *, config=None, build_dir=None, resume=False, max_games=None):
    import slater_model_selection as s
    run = s.run_path(name)
    with s.process_lock(s.BASE / 'locks' / (name + '.lock')):
        if resume:
            saved = s.read_json(run / 'config.json')
            if not saved or not saved['settings'].get('goal_race'):
                raise ValueError('Not an existing goal benchmark')
            protocol = s.read_json(run / 'protocol.json')
            (run / 'PAUSE').unlink(missing_ok=True)
            if protocol is None:
                if saved['identity'] != s.selector_identity(build_dir):
                    raise ValueError('Code/native identity changed during inventory; start a fresh run')
                protocol = s.finish_inventory(run, saved['settings'], saved['identity'])
        else:
            run, protocol = s.initialize(name, config, build_dir)
        if protocol is None:
            return s.read_json(run / 'progress.json')
        inventory = s.verify_run(run, protocol, build_dir)
        cfg = protocol['settings']['goal_race']
        if not cfg:
            raise ValueError('Goal benchmark configuration required')
        if inventory['roles']['baseline'] not in inventory['candidate_ids']:
            raise ValueError('Baseline must be among the benchmark candidates')
        jobs, records = load_ledger(run)
        wave_dir = run / 'goal_rounds'; wave_dir.mkdir(exist_ok=True)
        consumed = 0
        while True:
            report = summarize(run, protocol, inventory, records)
            reason = ('PAUSED' if (run / 'PAUSE').exists() else
                      'GAME_BUDGET_REACHED' if max_games is not None and consumed >= max_games else None)
            if report['complete'] or reason:
                s.verify_run(run, protocol, build_dir)
                return summarize(run, protocol, inventory, records, None if report['complete'] else reason)
            pending = [job for key, job in jobs.items() if key not in records]
            if pending:
                # A saved wave is completed before any next pair is planned.
                wave = next(p for p in wave_paths(wave_dir)
                            if any(j['id'] not in records for j in s.read_json(p)['jobs']))
                todo = [j for j in s.read_json(wave)['jobs'] if j['id'] not in records]
            else:
                budget = protocol['settings']['job_group']
                if max_games is not None:
                    budget = min(budget, max_games - consumed)
                if budget < 2:
                    return summarize(run, protocol, inventory, records, 'GAME_BUDGET_REACHED')
                todo = []
                # One fresh color pair per active cell, in round-robin waves.
                for row in sorted(report['models'], key=lambda r: min(m['rounds'] for m in r['formats'].values())):
                    for mode, cell in row['formats'].items():
                        if cell['status'] != 'EVALUATING' or len(todo) + 2 > budget:
                            continue
                        for color in ('blue', 'orange'):
                            todo.append(make_job(protocol, row['id'], inventory['roles']['rival:nexto'],
                                                 mode, cell['rounds'] // 2, color))
                if not todo:
                    raise RuntimeError('No eligible rounds despite an incomplete benchmark')
                wave = wave_dir / f'wave_{len(wave_paths(wave_dir)):06d}.json'
                s.atomic_json(wave, {'jobs': todo})
                jobs.update({j['id']: j for j in todo})
            if max_games is not None:
                todo = todo[:max_games-consumed]
            before = len(records)
            records.update(execute_wave(run, protocol, inventory, todo, wave, build_dir))
            gained = len(records) - before
            consumed += gained
            if not gained and not (run / 'PAUSE').exists():
                raise RuntimeError('Native goal evaluator returned without completing a round')
            print('GOAL_BENCHMARK_PROGRESS', json.dumps({'rounds': len(records), 'new_rounds': gained}), flush=True)
