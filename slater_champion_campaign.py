"""Resumeable, bounded champion branches with cached paired evaluation.

The experiment champion is a private immutable actor. A new training routine
always branches from that champion; exploratory training never overwrites the
playing model. Fresh confirmation seeds are consumed once per branch.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import time

import numpy as np
import torch

import slater_model_selection as selector
import slater_native_attention as native
from slater_v041_core import atomic_json, process_lock, read_json, sha256

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/isolated/champion_campaigns'
ROUTINES = ('match', 'defense', 'wall-reset', 'air-control', 'recovery',
            'boost', 'bump', 'bump-evasion')
SCHEMA = 1


def default_config():
    profile = deepcopy(native.PROFILE)
    if 'selfplay_refresh' in profile:
        profile['selfplay_refresh'] = 10
    return {
        'cycles': 8, 'chunk_updates': 20, 'branch_updates': 100,
        'screen_every': 5, 'plateau_chunks': 3, 'regression_chunks': 2,
        'max_minutes': 0., 'unlimited_until_paused': False,
        'routines': list(ROUTINES), 'native_profile': profile,
        'routine_profiles': {}, 'rivals': {'nexto': str(native.DEFAULT_RIVAL)},
        'formats': ['1v1', '2v2', '3v3'], 'rivals_by_format': {},
        'learner_scripted_kickoff': False, 'require_target_advantage': False,
        'mode_weights': {'1v1': .4, '2v2': .3, '3v3': .3},
        'screen_seeds': 2, 'screen_seconds': 20.,
        'confirm_seeds': 8, 'confirm_seconds': 60.,
        'worlds': 8, 'job_group': 128, 'seed_base': 740_000_000,
        'min_improvement': .05, 'mode_regression_margin': .5,
        'screen_regression_margin': .5, 'promotion_alpha': .05,
        'min_disk_gb': .5, 'history_opponents': 4,
    }


def run_path(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
        raise ValueError('Use an ASCII campaign name of 1..40 letters, numbers, underscore or hyphen')
    return BASE / name


def merge_config(changes=None):
    cfg = default_config()
    for key, value in (changes or {}).items():
        if key not in cfg:
            raise ValueError('Unknown champion campaign setting: ' + key)
        if key == 'native_profile':
            cfg[key].update(value)
        else:
            cfg[key] = deepcopy(value)
    return cfg


def validate_config(changes=None):
    cfg = merge_config(changes)
    for key, low, high in (('cycles', 0, 10000), ('chunk_updates', 1, 10000),
                           ('branch_updates', 1, 100000), ('screen_every', 1, 10000),
                           ('plateau_chunks', 1, 100), ('regression_chunks', 1, 100),
                           ('screen_seeds', 1, 64), ('confirm_seeds', 1, 64),
                           ('worlds', 1, 32), ('job_group', 1, 1024),
                           ('history_opponents', 0, 16),
                           ('seed_base', 1, 1_500_000_000)):
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    for key, low, high in (('max_minutes', 0., 100000.), ('screen_seconds', .1, 300.),
                           ('confirm_seconds', .1, 300.), ('min_improvement', 0., 20.),
                           ('mode_regression_margin', 0., 20.), ('screen_regression_margin', 0., 20.),
                           ('promotion_alpha', .000001, .2), ('min_disk_gb', 0., 100.)):
        if type(cfg[key]) not in (int, float) or not math.isfinite(cfg[key]) or not low <= cfg[key] <= high:
            raise ValueError('Invalid ' + key)
    if type(cfg['unlimited_until_paused']) is not bool:
        raise ValueError('unlimited_until_paused must be a boolean')
    if cfg['cycles'] == 0 and cfg['max_minutes'] == 0 and not cfg['unlimited_until_paused']:
        raise ValueError('cycles=0 requires a time budget or explicit unlimited_until_paused=true')
    if not isinstance(cfg['routines'], list) or not cfg['routines'] or set(cfg['routines']) - set(ROUTINES):
        raise ValueError('Queue only implemented native routines: ' + ', '.join(ROUTINES))
    cfg['formats'] = [list(fmt) for fmt in selector.stage_formats(cfg['formats'])]
    modes = {f'{ours}v{theirs}' for ours, theirs in cfg['formats']}
    if set(cfg['mode_weights']) != modes:
        raise ValueError('mode_weights must contain exactly the configured formats')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
           for v in cfg['mode_weights'].values()):
        raise ValueError('Mode weights must be positive and finite')
    total = sum(cfg['mode_weights'].values())
    cfg['mode_weights'] = {key: value / total for key, value in cfg['mode_weights'].items()}
    if not isinstance(cfg['rivals'], dict) or not cfg['rivals']:
        raise ValueError('At least one exact frozen rival is required')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name) for name in cfg['rivals']):
        raise ValueError('Rival names must be simple ASCII names')
    cfg['rivals'] = {name: str(selector.path_of(path)) for name, path in cfg['rivals'].items()}
    if type(cfg['learner_scripted_kickoff']) is not bool:
        raise ValueError('learner_scripted_kickoff must be a boolean')
    mapping = cfg['rivals_by_format']
    if not isinstance(mapping, dict) or (mapping and set(mapping) != modes):
        raise ValueError('rivals_by_format must cover every configured format')
    for names in mapping.values():
        if (not isinstance(names, list) or not names or len(names) != len(set(names))
                or any(name not in cfg['rivals'] for name in names)):
            raise ValueError('Per-format rivals must be nonempty lists of configured rival names')
    if type(cfg['require_target_advantage']) is not bool or (cfg['require_target_advantage'] and not mapping):
        raise ValueError('require_target_advantage needs explicit per-format rivals')
    if set(cfg['native_profile']) != set(native.PROFILE):
        raise ValueError('native_profile contains missing or unknown trainer settings')
    cfg['native_profile'] = native.validate_profile(cfg['native_profile'])
    if not isinstance(cfg['routine_profiles'], dict) or set(cfg['routine_profiles']) - set(ROUTINES):
        raise ValueError('routine_profiles must name implemented routines')
    for options in cfg['routine_profiles'].values():
        if not isinstance(options, dict) or set(options) - set(native.PROFILE):
            raise ValueError('Unknown native routine setting')
        native.validate_profile({**cfg['native_profile'], **options})
    for key in ('screen_seconds', 'confirm_seconds'):
        cfg[key] = math.floor(cfg[key] * 120 + .5) / 120
    return cfg


def campaign_identity(build_dir=None):
    torch.set_num_threads(1)
    return {**selector.selector_identity(build_dir), 'campaign_sha256': sha256(__file__)}


def verify_files(entries):
    for entry in entries:
        if not Path(entry['path']).is_file() or sha256(entry['path']) != entry['sha256']:
            raise ValueError('Protected campaign input changed: ' + entry['path'])


def portable_model(source, run, inventory):
    source = Path(source).resolve()
    model, entry = selector.canonical_actor(
        selector.load_actor(ROOT, native.DEFAULT_RIVAL).eval(),
        {'path': str(source), 'families': ['campaign'], 'roles': []},
        run / 'actors', inventory['models'])
    saved = inventory['models'].setdefault(model['id'], {**model, 'source_paths': [],
                                                         'families': ['campaign'], 'roles': []})
    if not any(previous['path'] == entry['path'] for previous in saved['source_paths']):
        saved['source_paths'].append(entry)
    atomic_json(run / 'inventory.json', inventory)
    return model['id']


def initialize(name, *, source=None, selection=None, config=None, build_dir=None):
    if (source is None) == (selection is None):
        raise ValueError('Choose exactly one --source checkpoint or complete --selection report')
    run = run_path(name)
    if run.exists():
        raise FileExistsError('Campaign exists; use resume or a new run name: ' + str(run))
    cfg = validate_config(config)
    identity = campaign_identity(build_dir)
    selection_metadata = None
    if selection is not None:
        source, selection_metadata = native.source_from_selection(selection)
    source = native.validate_source(source)
    protected = [{'path': str(source), 'sha256': sha256(source)}]
    playing_model = str(source)
    if selection_metadata:
        playing_model = selection_metadata['playing_model']
        protected += selection_metadata.get('source_paths', [])
        playing_source = native.validate_source(playing_model)
        protected.append({'path': str(playing_source), 'sha256': sha256(playing_source)})
    for path in cfg['rivals'].values():
        path = native.validate_source(path)
        protected.append({'path': str(path), 'sha256': sha256(path)})
    run.mkdir(parents=True)
    if selection_metadata:
        origin = selection_metadata['path']
        snapshot = run / 'source_selection.json'
        native.snapshot_json(origin, snapshot, expected_sha256=selection_metadata['sha256'])
        selection_metadata = {**selection_metadata, 'origin_path': origin, 'path': str(snapshot)}
        protected.append({'path': str(snapshot), 'sha256': selection_metadata['sha256']})
    inventory = {'models': {}, 'roles': {}}
    champion_id = portable_model(source, run, inventory)
    inventory['roles']['baseline'] = champion_id
    for rival, path in cfg['rivals'].items():
        inventory['roles']['rival:' + rival] = portable_model(path, run, inventory)
    atomic_json(run / 'inventory.json', inventory)
    protocol = {'schema': SCHEMA, 'settings': cfg, 'identity': identity,
                'protected_inputs': protected, 'playing_model': playing_model,
                'initial_champion_id': champion_id,
                'learner_scripted_kickoff': cfg['learner_scripted_kickoff'], 'frozen_scripted_kickoff': True,
                'confirmation_is_independent_per_branch': True,
                'source_selection': selection_metadata,
                'playing_model_auto_export': False}
    protocol['protocol_sha'] = selector.canonical_hash(protocol)
    atomic_json(run / 'protocol.json', protocol)
    state = {'schema': SCHEMA, 'status': 'INITIALIZED', 'phase': 'branch_start',
             'cycle': 0, 'champion_id': champion_id, 'promotions': 0,
             'branches': [], 'active': None, 'elapsed_seconds': 0.,
             'train_updates': 0, 'evaluation_games': 0,
             'playing_model': playing_model, 'all_checkpoints_preserved': True}
    save_state(run, state, inventory)
    return run, protocol, state, inventory


def verify_run(run, build_dir=None):
    protocol = read_json(run / 'protocol.json')
    if not protocol or protocol.get('schema') != SCHEMA:
        raise ValueError('No compatible champion campaign protocol')
    body = {key: value for key, value in protocol.items() if key != 'protocol_sha'}
    if selector.canonical_hash(body) != protocol['protocol_sha']:
        raise ValueError('Campaign protocol changed')
    if protocol['identity'] != campaign_identity(build_dir):
        raise ValueError('Campaign code, binary or runtime changed; preserve it and create a new run')
    verify_files(protocol['protected_inputs'])
    inventory = read_json(run / 'inventory.json')
    for model in inventory['models'].values():
        if sha256(model['actor_path']) != model['exported_sha256']:
            raise ValueError('Private campaign actor changed: ' + model['actor_path'])
        verify_files(model['source_paths'])
    return protocol, read_json(run / 'progress.json'), inventory


def save_state(run, state, inventory):
    champion = inventory['models'][state['champion_id']]
    active = state.get('active') or {}
    state.update(champion=champion['actor_path'], routine=active.get('routine'),
                 branch_run=active.get('run_name'), branch_updates=active.get('updates', 0),
                 plateau=active.get('plateau', 0),
                 checkpoint=active.get('latest_checkpoint'))
    atomic_json(run / 'progress.json', state)
    atomic_json(run / 'selected.json', {'schema': SCHEMA, 'model_id': champion['id'],
                'actor_path': champion['actor_path'], 'actor_weights_sha256': champion['actor_weights_sha256'],
                'exported_sha256': champion['exported_sha256'],
                'source_paths': champion['source_paths'], 'promotions': state['promotions'],
                'playing_model': state['playing_model'], 'playing_model_unchanged': True,
                'status': 'CONFIRMED_SIMULATOR_CHAMPION' if state['promotions'] else 'INITIAL_BASELINE',
                'confirmed_best': False})
    shortlist = {'champion': champion, 'branches': state['branches'],
                 'active': state.get('active'), 'all_checkpoints_preserved': True,
                 'playing_model': state['playing_model']}
    atomic_json(run / 'shortlist.json', shortlist)
    lines = ['# Automatic champion campaign', '',
             'Every checkpoint is retained. Confirmed simulator improvements do not automatically export a playing bot.',
             '', f"Status: {state['status']} · cycle {state['cycle']} · promotions {state['promotions']}",
             '', 'Experiment champion: `' + champion['actor_path'] + '`', '',
             '| Branch | Routine | Updates | Result | Best candidate |',
             '| --- | --- | ---: | --- | --- |']
    for branch in state['branches']:
        lines.append(f"| {branch['cycle']} | {branch['routine']} | {branch['updates']} | "
                     f"{branch['result']} | {branch['best_id']} |")
    if active:
        lines += ['', f"Active branch: `{active['run_name']}` ({active['updates']} updates).",
                  'Parent actor: `' + inventory['models'][active['parent_id']]['actor_path'] + '`']
    lines += ['', 'Read each branch screen.json and confirmation.json for mode-specific scores and seed evidence.', '']
    (run / 'SHORTLIST.md').write_text('\n'.join(lines), encoding='utf-8')


def evaluation_protocol(protocol, cfg):
    return {'protocol_sha': protocol['protocol_sha'], 'identity': protocol['identity'],
            'settings': {'device': cfg['native_profile']['device'] if cfg['native_profile']['device'] != 'auto'
                         else 'cuda' if torch.cuda.is_available() else 'cpu',
                         'worlds': cfg['worlds'], 'learner_scripted_kickoff': cfg['learner_scripted_kickoff'],
                         'frozen_scripted_kickoff': True}}


def seed_namespace(cfg, cycle, stage):
    """New confirmation data is never reused for screening or a later branch."""
    base = cfg['seed_base'] + (cycle - 1) * 10000 + (0 if stage == 'screen' else 5000)
    count = cfg['screen_seeds' if stage == 'screen' else 'confirm_seeds']
    return [base + 31 * index for index in range(count)]


def evaluation_jobs(protocol, inventory, cfg, candidate_ids, parent_id, cycle, stage):
    evaluation = evaluation_protocol(protocol, cfg)
    seconds = cfg['screen_seconds' if stage == 'screen' else 'confirm_seconds']
    jobs = []
    for fmt in cfg['formats']:
        mode = f'{fmt[0]}v{fmt[1]}'
        names = cfg['rivals_by_format'].get(mode, list(cfg['rivals']))
        rivals = list(dict.fromkeys([inventory['roles']['rival:' + name] for name in names] + [parent_id]))
        jobs.extend(selector.game_descriptor(evaluation, candidate, rival, candidate, fmt, seed, side,
                                            seconds, 'candidate_squad')
                    for candidate in sorted(set(candidate_ids) | {parent_id}) for rival in rivals
                    for seed in seed_namespace(cfg, cycle, stage) for side in ('blue', 'orange'))
    return jobs


def weighted_ranking(records, candidate_ids, parent_id, cfg, *, alpha=.05):
    """Pair by seed/start/opponent/color, then weight modes before intervals."""
    rankings = selector.summarize(records, candidate_ids, parent_id, comparison_count=1)
    parent_cells = {selector.cell_key(row): row for row in records if row['candidate_id'] == parent_id}
    for ranking in rankings:
        modes = {}
        for row in records:
            if row['candidate_id'] != ranking['id']:
                continue
            paired = parent_cells[selector.cell_key(row)]
            delta = ((row['goals_for'] - row['goals_against'])
                     - (paired['goals_for'] - paired['goals_against'])) * 60 / row['seconds']
            mode = f"{row['format'][0]}v{row['format'][1]}"
            modes.setdefault(mode, {}).setdefault(row['seed'], []).append(delta)
        if set(modes) != set(cfg['mode_weights']):
            raise ValueError('Every configured mode needs paired evaluation evidence')
        seeds = set.intersection(*(set(values) for values in modes.values()))
        if any(set(values) != seeds for values in modes.values()):
            raise ValueError('Modes must use the same independent seed clusters')
        weighted = [sum(cfg['mode_weights'][mode] * float(np.mean(values[seed]))
                        for mode, values in modes.items()) for seed in sorted(seeds)]
        ranking['weighted_goal_difference_per_minute'] = selector.clustered_interval(weighted, alpha=alpha)
        ranking['weighted_seed_means'] = {str(seed): value for seed, value in zip(sorted(seeds), weighted)}
        ranking['per_mode'] = {mode: selector.clustered_interval(
            [float(np.mean(values[seed])) for seed in sorted(seeds)], alpha=alpha)
            for mode, values in modes.items()}
        ranking['confirmed_best'] = False
    # Equal scores keep the parent. A branch cannot be promoted for winning a lexical tie.
    return sorted(rankings, key=lambda row: (-row['weighted_goal_difference_per_minute']['mean'],
                                            row['id'] != parent_id, row['id']))


def promotion_decision(ranking, parent_id, cfg, cycle):
    candidate = next((row for row in ranking if row['id'] != parent_id), None)
    if candidate is None:
        return {'promote': False, 'reason': 'PARENT_RETAINED', 'candidate_id': parent_id}
    overall = candidate['weighted_goal_difference_per_minute']
    if overall['independent_seeds'] < 8:
        return {'promote': False, 'reason': 'INSUFFICIENT_INDEPENDENT_SEEDS', 'candidate_id': candidate['id']}
    if overall['lower'] is None or overall['lower'] <= cfg['min_improvement']:
        return {'promote': False, 'reason': 'INCONCLUSIVE_OR_NO_IMPROVEMENT', 'candidate_id': candidate['id']}
    regressed = [mode for mode, interval in candidate['per_mode'].items()
                 if interval['lower'] is None or interval['lower'] < -cfg['mode_regression_margin']]
    if regressed:
        return {'promote': False, 'reason': 'MODE_REGRESSION_OR_UNCERTAINTY',
                'candidate_id': candidate['id'], 'modes': regressed}
    if cfg['require_target_advantage']:
        expected = {f'{mode}:{name}' for mode, names in cfg['rivals_by_format'].items() for name in names}
        scores = candidate.get('target_scores', {})
        failed = sorted(key for key in expected if key not in scores or scores[key]['lower'] is None
                        or scores[key]['lower'] <= 0)
        if failed:
            return {'promote': False, 'reason': 'TARGET_ADVANTAGE_NOT_CONFIRMED',
                    'candidate_id': candidate['id'], 'targets': failed}
    return {'promote': True, 'reason': 'FRESH_SEED_IMPROVEMENT', 'candidate_id': candidate['id'],
            'cycle': cycle, 'scope': 'configured simulator rivals and formats; competitive rank unverified'}


def evaluate_branch(run, protocol, inventory, state, cfg, stage, candidate_ids, build_dir=None):
    branch = state['active']; parent = branch['parent_id']
    folder = run / 'branches' / f"cycle_{state['cycle']:06d}"
    folder.mkdir(parents=True, exist_ok=True)
    jobs = evaluation_jobs(protocol, inventory, cfg, candidate_ids, parent, state['cycle'], stage)
    evaluation = evaluation_protocol(protocol, cfg)
    local_inventory = {**inventory, 'roles': {**inventory['roles'], 'baseline': parent}}
    group_stage = f"cycle_{state['cycle']:06d}_{stage}"
    while True:
        records, missing = selector.cached_records(run, jobs)
        state.update(status='EVALUATING', phase=stage, completed_games=len(records),
                     total_games=len(jobs))
        save_state(run, state, inventory)
        if not missing:
            break
        if (run / 'PAUSE').exists():
            return None
        # Complete parent games first; selectors can then rank partial child groups safely.
        missing.sort(key=lambda job: (job['candidate_id'] != parent, job['candidate_id'], job['id']))
        group = missing[:cfg['job_group']]
        before = len(records)
        selector.execute_group(run, evaluation, local_inventory, group_stage, group, build_dir)
        after, _ = selector.cached_records(run, jobs)
        gained = len(after) - before
        state['evaluation_games'] += gained
        if not gained and not (run / 'PAUSE').exists():
            raise RuntimeError('Native evaluation completed without a new cached match')
    # Alpha spending controls repeated branch confirmations; each mode and overall
    # comparison receives its own share. Bootstrap coverage remains approximate.
    target_count = sum(map(len, cfg['rivals_by_format'].values())) if cfg['require_target_advantage'] else 0
    alpha = (cfg['promotion_alpha'] / (state['cycle'] * (state['cycle'] + 1))
             / (1 + len(cfg['formats']) + target_count)) if stage == 'confirm' else .05
    ranking = weighted_ranking(records, candidate_ids, parent, cfg, alpha=alpha)
    for candidate in ranking:
        candidate['target_scores'] = {}
        for mode, names in cfg['rivals_by_format'].items():
            for name in names:
                rival = inventory['roles']['rival:' + name]
                groups = {}
                for record in records:
                    if (record['candidate_id'] == candidate['id'] and record['rival_id'] == rival
                            and f"{record['format'][0]}v{record['format'][1]}" == mode):
                        score = (record['goals_for'] - record['goals_against']) * 60 / record['seconds']
                        groups.setdefault(record['seed'], []).append(score)
                candidate['target_scores'][f'{mode}:{name}'] = selector.clustered_interval(
                    [float(np.mean(scores)) for scores in groups.values()], alpha=alpha)
    report = {'schema': SCHEMA, 'stage': stage, 'complete': True, 'cycle': state['cycle'],
              'parent_id': parent, 'ranking': ranking, 'seeds': seed_namespace(cfg, state['cycle'], stage),
              'alpha': alpha, 'completed_games': len(records), 'team_policy': 'candidate_squad',
              'learner_scripted_kickoff': cfg['learner_scripted_kickoff'], 'frozen_scripted_kickoff': True,
              'all_checkpoints_preserved': True, 'competitive_rank_verified': False}
    atomic_json(folder / ('screen.json' if stage == 'screen' else 'confirmation.json'), report)
    return report


def branch_profile(cfg, routine, cycle):
    profile = {**cfg['native_profile'], **cfg['routine_profiles'].get(routine, {})}
    profile['learner_scripted_kickoff'] = cfg['learner_scripted_kickoff']
    profile['seed'] = (cfg['native_profile']['seed'] - 1 + cycle * 997) % (2**31 - 1) + 1
    if 'routine' in native.PROFILE:
        profile['routine'] = routine
        profile['curriculum'] = 'wall-reset' if routine in ('wall-reset', 'air-control') else 'none'
    elif routine in ('match', 'wall-reset'):
        profile['curriculum'] = 'none' if routine == 'match' else 'wall-reset'
    else:
        raise ValueError('This trainer build does not implement routine ' + routine)
    if 'formats' in native.PROFILE:
        profile['formats'] = ','.join(f'{ours}v{theirs}' for ours, theirs in cfg['formats'])
    return native.validate_profile(profile)


def start_branch(name, run, protocol, state, inventory, cfg, build_dir=None):
    cycle = state['cycle'] + 1
    routine = cfg['routines'][(cycle - 1) % len(cfg['routines'])]
    branch_name = f'{name}_c{cycle:04d}'
    profile = branch_profile(cfg, routine, cycle)
    if 'opponent_pool' in native.PROFILE:
        history = [branch['champion_after'] for branch in state['branches']
                   if branch['promotion']['promote']]
        history = history[-cfg['history_opponents']:] if cfg['history_opponents'] else []
        opponent_ids = list(dict.fromkeys([value for key, value in inventory['roles'].items()
                                          if key.startswith('rival:')]
                                         + [state['champion_id']] + history))
        pool = run / 'branches' / f'cycle_{cycle:06d}' / 'opponent_pool.json'
        atomic_json(pool, {'actors': [{'id': 'p_' + id[2:26], 'path': inventory['models'][id]['actor_path']}
                                      for id in opponent_ids],
                          'rivals_by_format': {
                              mode: list(dict.fromkeys('p_' + id[2:26] for id in
                                  [inventory['roles']['rival:' + name] for name in names]
                                  + [state['champion_id']] + history))
                              for mode, names in cfg['rivals_by_format'].items()}})
        profile['opponent_pool'] = str(pool)
    state.update(cycle=cycle, phase='training', status='BRANCH_INITIALIZING', active={
        'cycle': cycle, 'routine': routine, 'run_name': branch_name,
        'parent_id': state['champion_id'], 'profile': profile,
        'updates': 0, 'plateau': 0, 'regression': 0, 'best_mean': 0.,
        'candidate_ids': [state['champion_id']], 'checkpoint_paths': [],
        'best_id': state['champion_id'], 'chunk_target': min(cfg['chunk_updates'], cfg['branch_updates'])})
    save_state(run, state, inventory)
    ensure_native_branch(state['active'], inventory, build_dir)


def ensure_native_branch(branch, inventory, build_dir=None):
    folder = native.run_path(branch['run_name'])
    if (folder / 'protocol.json').is_file():
        return native.check_run(branch['run_name'], build_dir)
    if folder.exists():
        raise RuntimeError('Interrupted branch initialization has no complete protocol; '
                           'preserve its folder and choose a new campaign name')
    parent = inventory['models'][branch['parent_id']]['actor_path']
    rival = inventory['models'][next(value for key, value in inventory['roles'].items()
                                    if key.startswith('rival:'))]['actor_path']
    return native.initialize_run(branch['run_name'], parent, teacher=parent, rival=rival,
                                 profile=branch['profile'], build_dir=build_dir)


def checkpoint_count(path):
    return int(Path(path).name.removeprefix('checkpoint_'))


def train_chunk(run, state, inventory, build_dir=None):
    branch = state['active']
    folder, protocol = ensure_native_branch(branch, inventory, build_dir)
    try:
        latest = native.latest_checkpoint(folder)
    except ValueError:
        latest = None
    current = checkpoint_count(latest) if latest else 0
    target = branch['chunk_target']
    if current > target:
        raise ValueError('Native branch was advanced outside its campaign; use a new campaign')
    if current < target:
        for partial in (folder / 'checkpoints').glob('checkpoint_*.partial'):
            partial.rename(partial.with_name(partial.name + '.interrupted_' + str(time.time_ns())))
        command = native.native_command('train', folder, protocol['profile'], build_dir=build_dir,
                                        checkpoint=latest, updates=target - current)
        # One pause file controls both the manager and its active C++ worker.
        command[command.index('--pause') + 1] = run / 'PAUSE'
        logfile = folder / f'campaign_training_{time.time_ns()}.log'
        with process_lock(folder / 'runner.lock'):
            result = native.checked_process(command, logfile, marker='SLATER_ATTENTION_COMPLETE',
                                            pause=run / 'PAUSE')
        latest = native.latest_checkpoint(folder)
        native.verify_protected(protocol)
        atomic_json(folder / 'session_summary.json', {**result, 'checkpoint': str(latest),
                    'source_unchanged': True, 'campaign': str(run), 'auto_promotion': False})
        if checkpoint_count(latest) == current and not (run / 'PAUSE').exists():
            raise RuntimeError('Native training stopped without saving another update: '
                               + str(result.get('status', result)))
    old = branch['updates']
    branch['updates'] = checkpoint_count(latest)
    state['train_updates'] += branch['updates'] - old
    branch['latest_checkpoint'] = str(latest)
    return branch['updates'] >= target


def collect_candidates(run, state, inventory, cfg):
    branch = state['active']
    folder = native.run_path(branch['run_name'])
    for path in sorted((folder / 'checkpoints').glob('checkpoint_*')):
        try:
            native.complete_checkpoint(path)
        except ValueError:
            continue
        count = checkpoint_count(path)
        if count > branch['updates'] or (count % cfg['screen_every'] and count != branch['updates']):
            continue
        if str(path) not in branch['checkpoint_paths']:
            id = portable_model(path / 'actor.pt', run, inventory)
            branch['candidate_ids'].append(id)
            branch['checkpoint_paths'].append(str(path))
        else:
            id = next(model['id'] for model in inventory['models'].values()
                      if any(entry['path'] == str((path / 'actor.pt').resolve())
                             for entry in model['source_paths']))
        if str(path) == branch['latest_checkpoint']:
            branch['latest_id'] = id
    branch['candidate_ids'] = sorted(set(branch['candidate_ids']))
    return branch['candidate_ids']


def apply_screen(state, report, cfg):
    branch = state['active']
    best = report['ranking'][0]
    best_mean = best['weighted_goal_difference_per_minute']['mean']
    improved = best_mean > branch['best_mean'] + cfg['min_improvement']
    branch['plateau'] = 0 if improved else branch['plateau'] + 1
    branch['best_mean'] = max(branch['best_mean'], best_mean)
    branch['best_id'] = best['id']
    latest = next(row for row in report['ranking'] if row['id'] == branch['latest_id'])
    latest_mean = latest['weighted_goal_difference_per_minute']['mean']
    branch['latest_mean'] = latest_mean
    branch['regression'] = branch['regression'] + 1 if latest_mean < -cfg['screen_regression_margin'] else 0
    branch['screen_shortlist'] = [row['id'] for row in report['ranking'][:4]]
    stop = ('REGRESSING_BRANCH' if branch['regression'] >= cfg['regression_chunks'] else
            'PLATEAU_BRANCH' if branch['plateau'] >= cfg['plateau_chunks'] else
            'BRANCH_BUDGET_REACHED' if branch['updates'] >= cfg['branch_updates'] else None)
    branch['stop_reason'] = stop
    if stop:
        state['phase'] = 'confirm' if best['id'] != branch['parent_id'] and best_mean > 0 else 'branch_close'
    else:
        branch['chunk_target'] = min(branch['updates'] + cfg['chunk_updates'], cfg['branch_updates'])
        state['phase'] = 'training'


def close_branch(run, state, inventory, decision=None):
    branch = state['active']
    decision = decision or {'promote': False, 'reason': 'PARENT_RETAINED', 'candidate_id': branch['parent_id']}
    if decision['promote']:
        state['champion_id'] = decision['candidate_id']
        state['promotions'] += 1
    branch.update(result=decision['reason'], promotion=decision,
                  champion_after=state['champion_id'])
    atomic_json(run / 'branches' / f"cycle_{state['cycle']:06d}" / 'decision.json', branch)
    state['branches'].append(branch)
    state['active'] = None
    state.update(phase='branch_start', status='BRANCH_COMPLETE')
    save_state(run, state, inventory)


def request_pause(name):
    run = run_path(name)
    if not (run / 'protocol.json').is_file():
        raise ValueError('No champion campaign is available to pause')
    (run / 'PAUSE').touch()
    return {'status': 'PAUSE_REQUESTED', 'run': str(run),
            'note': 'Wait for the current update or game to save and the manager to report PAUSED.'}


def status(name):
    run = run_path(name)
    return {'progress': read_json(run / 'progress.json', {'status': 'NOT_FOUND'}),
            'selected': read_json(run / 'selected.json'), 'run': str(run),
            'shortlist': str(run / 'SHORTLIST.md')}


def run_campaign(name, *, source=None, selection=None, config=None, build_dir=None, resume=False):
    run = run_path(name)
    with process_lock(BASE / 'locks' / (name + '.lock')):
        if resume:
            if source is not None or selection is not None:
                raise ValueError('Resume uses the protected campaign source; omit source and selection')
            protocol, state, inventory = verify_run(run, build_dir)
            if config is not None and validate_config(config) != protocol['settings']:
                raise ValueError('Resume cannot change saved campaign settings')
            (run / 'PAUSE').unlink(missing_ok=True)
        else:
            run, protocol, state, inventory = initialize(name, source=source, selection=selection,
                                                        config=config, build_dir=build_dir)
        cfg = protocol['settings']; started = time.monotonic(); prior_elapsed = state['elapsed_seconds']
        try:
            while True:
                state['elapsed_seconds'] = prior_elapsed + time.monotonic() - started
                reason = ('PAUSED' if (run / 'PAUSE').exists() else
                          'TIME_BUDGET_REACHED' if cfg['max_minutes'] and state['elapsed_seconds'] >= cfg['max_minutes'] * 60 else
                          'DISK_FLOOR_REACHED' if shutil.disk_usage(run).free < cfg['min_disk_gb'] * 1024**3 else
                          'FINITE_CAMPAIGN_COMPLETE' if state['phase'] == 'branch_start' and cfg['cycles']
                          and state['cycle'] >= cfg['cycles'] else None)
                if reason:
                    state['status'] = reason; save_state(run, state, inventory)
                    verify_run(run, build_dir)
                    return state
                phase = state['phase']
                if phase == 'branch_start':
                    start_branch(name, run, protocol, state, inventory, cfg, build_dir)
                elif phase == 'training':
                    state['status'] = 'TRAINING'; save_state(run, state, inventory)
                    complete = train_chunk(run, state, inventory, build_dir)
                    if complete:
                        collect_candidates(run, state, inventory, cfg)
                        state['phase'] = 'screen'
                    save_state(run, state, inventory)
                elif phase == 'screen':
                    report = evaluate_branch(run, protocol, inventory, state, cfg, 'screen',
                                             state['active']['candidate_ids'], build_dir)
                    if report:
                        apply_screen(state, report, cfg); save_state(run, state, inventory)
                elif phase == 'confirm':
                    branch = state['active']
                    report = evaluate_branch(run, protocol, inventory, state, cfg, 'confirm',
                                             [branch['best_id'], branch['parent_id']], build_dir)
                    if report:
                        decision = promotion_decision(report['ranking'], branch['parent_id'], cfg, state['cycle'])
                        close_branch(run, state, inventory, decision)
                elif phase == 'branch_close':
                    close_branch(run, state, inventory)
                else:
                    raise ValueError('Unknown persisted campaign phase: ' + phase)
                print('CHAMPION_CAMPAIGN_PROGRESS', json.dumps({key: state.get(key) for key in
                      ('status', 'phase', 'cycle', 'routine', 'branch_updates', 'promotions', 'champion')}), flush=True)
        except KeyboardInterrupt:
            (run / 'PAUSE').touch()
            state.update(status='PAUSED', elapsed_seconds=prior_elapsed + time.monotonic() - started)
            save_state(run, state, inventory)
            return state
        except Exception as exc:
            state.update(status='ERROR', error=str(exc), elapsed_seconds=prior_elapsed + time.monotonic() - started)
            save_state(run, state, inventory)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'resume', 'status', 'pause', 'config'))
    parser.add_argument('--run')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--build-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'config':
        print(json.dumps(default_config(), indent=2)); return
    if not args.run:
        parser.error('--run is required')
    if args.command == 'status':
        result = status(args.run)
    elif args.command == 'pause':
        result = request_pause(args.run)
    else:
        result = run_campaign(args.run, source=args.source, selection=args.selection,
                              config=read_json(args.config) if args.config else None,
                              build_dir=args.build_dir, resume=args.command == 'resume')
    print('CHAMPION_CAMPAIGN_COMPLETE', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
