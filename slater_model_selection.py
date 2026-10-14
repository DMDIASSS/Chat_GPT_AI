"""Preserve, deduplicate and screen attention checkpoints in finite stages.

This is an experiment selector, not an automatic playing-model promotion.
Every native game has a content-derived identity and a durable cached record.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import time
import zipfile

import numpy as np
import torch

import slater_native_attention as native
from slater_mechanics_eval import load_actor
from slater_team_eval import parse_formats, policy_digest, runtime_identity
from slater_v041_core import atomic_json, process_lock, read_json, sha256

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/isolated/model_selection'
SCHEMA = 1
DEFAULT_278 = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000278.pt'
STAGES = ('screen', 'refine', 'finalists', 'confirm')
DEFAULT = {
    'goal_race': None,
    'baseline': str(native.DEFAULT_SOURCE),
    'anchors': {'update180': str(native.DEFAULT_SOURCE), 'update278': str(DEFAULT_278)},
    'families': {
        'mechanics': ['data/isolated/mechanics_curriculum/selected7_mechanics01/update_*.pt',
                      'data/isolated/mechanics_curriculum/selected7_mechanics01/accepted*.pt'],
        'team': ['data/isolated/team_campaigns/update180_teams01/update_*.pt'],
        'attention': ['data/isolated/native_attention/runs/update180_attention02/checkpoints/checkpoint_*'],
    },
    'rivals': {'nexto': str(native.DEFAULT_RIVAL), 'update180': str(native.DEFAULT_SOURCE),
               'update278': str(DEFAULT_278)},
    'device': 'auto', 'worlds': 8, 'job_group': 128, 'top_per_family': 4,
    'refine_per_family': 8, 'uncertain_extra_per_family': 4, 'confirm_leaders': 4,
    'learner_scripted_kickoff': False, 'frozen_scripted_kickoff': True,
    'stages': {
        'screen': {'seeds': [730000000], 'seconds': 20., 'formats': ['1v1'],
                   'rivals': ['nexto', 'update180'], 'team_policy': 'fixed_reference'},
        'refine': {'seeds': [731000000, 731000997], 'seconds': 30.,
                   'formats': ['1v1', '2v2', '3v3'], 'team_policy': 'fixed_reference'},
        'finalists': {'seeds': [732000000 + 997 * i for i in range(4)], 'seconds': 45.,
                      'formats': ['1v1', '2v2', '3v3'], 'head_to_head_per_family': 1,
                      'team_policy': 'candidate_squad'},
        'confirm': {'seeds': [733000000 + 997 * i for i in range(8)], 'seconds': 60.,
                    'formats': ['1v1', '2v2', '3v3'], 'team_policy': 'candidate_squad'},
    },
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def path_of(value):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def run_path(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ValueError('Use an ASCII run name with letters, numbers, underscore or hyphen')
    return BASE / 'runs' / name


def merge_config(base, changes):
    result = deepcopy(base)
    for key, value in changes.items():
        if key not in result:
            raise ValueError('Unknown selector setting: ' + key)
        # Model maps are authoritative replacements, not inferred additions.
        if key == 'stages':
            for name, options in value.items():
                if name not in STAGES:
                    raise ValueError('Unknown stage: ' + name)
                result[key][name].update(options)
        else:
            result[key] = value
    return result


def validate_config(config):
    cfg = deepcopy(config)
    if set(cfg) != set(DEFAULT):
        raise ValueError('Selector configuration has missing or unknown top-level settings')
    if cfg['goal_race'] is not None:
        from slater_nexto_goal_benchmark import validate_goal_config
        cfg['goal_race'] = validate_goal_config(cfg['goal_race'])
        if set(cfg['rivals']) != {'nexto'}:
            raise ValueError('Goal benchmark requires Nexto as the only rival')
    for key in ('anchors', 'families', 'rivals'):
        if not isinstance(cfg[key], dict) or (key != 'anchors' and not cfg[key]):
            raise ValueError('Expected a named nonempty ' + key + ' map')
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name) for name in cfg[key]):
            raise ValueError('Use simple ASCII names for ' + key)
    cfg['baseline'] = str(path_of(cfg['baseline']))
    for key in ('anchors', 'rivals'):
        cfg[key] = {name: str(path_of(value)) for name, value in cfg[key].items()}
    for family, patterns in cfg['families'].items():
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list) or not patterns or any(not isinstance(x, str) for x in patterns):
            raise ValueError('Each family needs one or more exact checkpoint globs')
        cfg['families'][family] = patterns
    for key, low, high in (('worlds', 1, 32), ('job_group', 1, 1024),
                           ('top_per_family', 1, 8), ('refine_per_family', 1, 32),
                           ('uncertain_extra_per_family', 0, 32), ('confirm_leaders', 1, 16)):
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    if cfg['refine_per_family'] < cfg['top_per_family']:
        raise ValueError('Refinement cannot retain fewer than the requested family shortlist')
    if cfg['device'] not in ('auto', 'cpu', 'cuda'):
        raise ValueError('Device must be auto, cpu or cuda')
    if cfg['device'] == 'auto':
        cfg['device'] = 'cuda' if torch.cuda.is_available() else 'cpu'
    if cfg['device'] == 'cuda' and not torch.cuda.is_available():
        raise ValueError('This PyTorch runtime cannot use CUDA')
    if type(cfg['learner_scripted_kickoff']) is not bool or cfg['frozen_scripted_kickoff'] is not True:
        raise ValueError('Learner kickoff must be explicit; frozen policies require scripted kickoff')
    if set(cfg['stages']) != set(STAGES):
        raise ValueError('All four selector stages must be configured')
    used_seeds = set()
    for name, stage in cfg['stages'].items():
        allowed = {'seeds', 'seconds', 'formats', 'rivals', 'head_to_head_per_family', 'team_policy'}
        if set(stage) - allowed:
            raise ValueError('Unknown stage setting in ' + name)
        seeds = stage['seeds']
        if (not isinstance(seeds, list) or not 1 <= len(seeds) <= 64
                or any(type(seed) is not int or not 0 <= seed < 2**31 - 100000 for seed in seeds)
                or len(set(seeds)) != len(seeds) or used_seeds.intersection(seeds)):
            raise ValueError('Stages require distinct independent seed namespaces')
        used_seeds.update(seeds)
        seconds = stage['seconds']
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not .1 <= seconds <= 300:
            raise ValueError('Stage seconds must be finite and between .1 and 300')
        stage['seconds'] = math.floor(seconds * 120 + .5) / 120
        stage['formats'] = [list(fmt) for fmt in stage_formats(stage['formats'])]
        if 'rivals' in stage:
            names = stage['rivals']
            if not isinstance(names, list) or not names or len(set(names)) != len(names) or set(names) - set(cfg['rivals']):
                raise ValueError('Stage rivals must name existing exact configured checkpoints')
        if type(stage.get('head_to_head_per_family', 0)) is not int or not 0 <= stage.get('head_to_head_per_family', 0) <= 2:
            raise ValueError('Head-to-head sampling is limited to 0..2 candidates per family')
        if stage.get('team_policy', 'fixed_reference') not in ('fixed_reference', 'candidate_squad'):
            raise ValueError('team_policy must be fixed_reference or candidate_squad')
        stage.setdefault('team_policy', 'fixed_reference')
    return cfg


def stage_formats(value):
    """Accept human-readable names without changing the existing team parser."""
    if isinstance(value, list) and value and isinstance(value[0], str):
        return parse_formats(','.join(value))
    return parse_formats(value)


def discovered_sources(config):
    sources = {}
    def add(path, family=None, role=None, checkpoint_folder=None):
        path = str(Path(path).resolve())
        item = sources.setdefault(path, {'path': path, 'families': [], 'roles': []})
        if family is not None and family not in item['families']:
            item['families'].append(family)
        if role is not None and role not in item['roles']:
            item['roles'].append(role)
        if checkpoint_folder:
            item['checkpoint_folder'] = str(checkpoint_folder)
    add(config['baseline'], role='baseline')
    for name, path in config['anchors'].items():
        add(path, role='anchor:' + name)
    for name, path in config['rivals'].items():
        add(path, role='rival:' + name)
    skipped = []
    for family, patterns in config['families'].items():
        for pattern in patterns:
            text = str(Path(pattern) if Path(pattern).is_absolute() else ROOT / pattern)
            for value in sorted(glob.glob(text)):
                path = Path(value).resolve()
                if path.is_dir():
                    try:
                        native.complete_checkpoint(path)
                    except ValueError as exc:
                        skipped.append({'path': str(path), 'family': family, 'reason': str(exc)})
                        continue
                    add(path / 'actor.pt', family=family, checkpoint_folder=path)
                elif path.is_file():
                    add(path, family=family)
    # Roles come first so missing anchors fail before a long inventory pass.
    return sorted(sources.values(), key=lambda x: (not bool(x['roles']), x['path'])), skipped


def selector_identity(build_dir=None):
    return {'schema': SCHEMA, 'native': native.binary_identity(build_dir),
            'code': {**native.code_identity(), 'slater_model_selection.py': sha256(__file__),
                     'slater_team_eval.py': sha256(ROOT / 'slater_team_eval.py'),
                     'slater_nexto_goal_benchmark.py': sha256(ROOT / 'slater_nexto_goal_benchmark.py'),
                     'slater_v041_worker.py': sha256(ROOT / 'slater_v041_worker.py')},
            'runtime': runtime_identity(), 'gigalearn_commit': native.helper.GIGA}


def weights_from_source(path):
    """Read plain tensor checkpoints safely; only trusted template code executes."""
    path = Path(path)
    is_script = False
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            is_script = any('/code/' in name for name in archive.namelist())
    if is_script:
        return torch.jit.load(str(path), map_location='cpu').state_dict()
    value = torch.load(path, map_location='cpu', weights_only=True)
    weights = value.get('actor') if isinstance(value, dict) else None
    if not isinstance(weights, dict):
        raise ValueError('Checkpoint does not contain an original attention actor state_dict')
    return weights


def canonical_actor(template, source, directory, known_exports=None):
    path = Path(source['path'])
    if not path.is_file():
        raise FileNotFoundError('Model checkpoint missing: ' + str(path))
    before = sha256(path)
    metadata = path.stat()
    weights = weights_from_source(path)
    expected = template.state_dict()
    if weights.keys() != expected.keys() or len(weights) != 44:
        raise ValueError('Only the original 44-tensor attention actor is supported')
    for name, value in weights.items():
        target = expected[name]
        if (not torch.is_tensor(value) or value.shape != target.shape or value.dtype != target.dtype
                or not torch.isfinite(value).all()):
            raise ValueError('Incompatible or nonfinite attention tensor: ' + name)
    template.load_state_dict(weights, strict=True)
    digest = policy_digest(template)
    destination = Path(directory) / (digest + '.pt')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix('.partial_' + str(time.time_ns()))
        torch.jit.save(template, str(temporary))
        restored = torch.jit.load(str(temporary), map_location='cpu')
        if policy_digest(restored) != digest:
            raise RuntimeError('Private portable actor changed weights')
        os.replace(temporary, destination)
    else:
        known = (known_exports or {}).get('a_' + digest)
        if known is not None:
            if sha256(destination) != known['exported_sha256']:
                raise RuntimeError('Existing private portable actor has changed')
        elif policy_digest(torch.jit.load(str(destination), map_location='cpu')) != digest:
            raise RuntimeError('Existing private portable actor has changed')
    if sha256(path) != before:
        raise RuntimeError('Checkpoint changed during inventory: ' + str(path))
    return {'id': 'a_' + digest, 'actor_weights_sha256': digest,
            'actor_path': str(destination.resolve()), 'exported_sha256': sha256(destination)}, {
                **source, 'sha256': before, 'bytes': metadata.st_size, 'mtime_ns': metadata.st_mtime_ns}


def finish_inventory(run, config, identity):
    source_doc = read_json(run / 'inputs.json')
    if not source_doc:
        sources, skipped = discovered_sources(config)
        source_doc = {'sources': sources, 'skipped': skipped}
        atomic_json(run / 'inputs.json', source_doc)
    work = read_json(run / 'inventory_work.json', {'models': {}, 'entries': [], 'rejected': source_doc['skipped']})
    input_paths = {entry['path'] for entry in source_doc['sources']}
    completed = ({entry['path'] for entry in work['entries']}
                 | {entry['path'] for entry in work['rejected']}) & input_paths
    started = time.monotonic()
    atomic_json(run / 'progress.json', {'status': 'INVENTORY', 'phase': 'inventory',
                'processed': len(completed), 'total': len(source_doc['sources']),
                'unique_actors': len(work['models'])})
    template = load_actor(ROOT, native.DEFAULT_RIVAL).eval()
    if len(list(template.parameters())) != 44 or sum(p.numel() for p in template.parameters()) != 444032:
        raise ValueError('Original attention template contract changed')
    for source in source_doc['sources']:
        if source['path'] in completed:
            continue
        if (run / 'PAUSE').exists():
            atomic_json(run / 'progress.json', {'status': 'PAUSED', 'phase': 'inventory',
                        'processed': len(completed), 'total': len(source_doc['sources'])})
            return None
        try:
            model, entry = canonical_actor(template, source, run / 'actors', work['models'])
        except Exception as exc:
            if source['roles']:
                raise RuntimeError(f'Required protected model failed inventory: {source["path"]}: {exc}') from exc
            work['rejected'].append({**source, 'reason': str(exc)})
        else:
            saved = work['models'].setdefault(model['id'], {**model, 'source_paths': [], 'families': [], 'roles': []})
            saved['source_paths'].append(entry)
            saved['families'] = sorted(set(saved['families']) | set(source['families']))
            saved['roles'] = sorted(set(saved['roles']) | set(source['roles']))
            work['entries'].append({**entry, 'id': model['id']})
        completed.add(source['path'])
        atomic_json(run / 'inventory_work.json', work)
        if len(completed) % 25 == 0 or len(completed) == len(source_doc['sources']) or source['roles']:
            atomic_json(run / 'progress.json', {'status': 'INVENTORY', 'phase': 'inventory',
                        'processed': len(completed), 'total': len(source_doc['sources']),
                        'unique_actors': len(work['models']), 'rejected': len(work['rejected'])})
            print('MODEL_INVENTORY', len(completed), '/', len(source_doc['sources']),
                  'unique', len(work['models']), 'duplicates', len(work['entries']) - len(work['models']),
                  'rejected', len(work['rejected']), 'seconds', round(time.monotonic() - started, 1), flush=True)
    models = work['models']
    role_ids = {role: model['id'] for model in models.values() for role in model['roles']}
    candidate_ids = sorted(model['id'] for model in models.values() if model['families'])
    if not candidate_ids:
        raise ValueError('No compatible family checkpoints were found; set exact family globs')
    protected_ids = sorted({role_ids['baseline']} | {id for role, id in role_ids.items() if role.startswith('anchor:')})
    inventory = {'schema': SCHEMA, 'models': models, 'candidate_ids': candidate_ids,
                 'protected_ids': protected_ids, 'roles': role_ids, 'rejected': work['rejected'],
                 'distinct_candidates': len(candidate_ids), 'source_files': len(work['entries']),
                 'aliases': len(work['entries']) - len(models), 'all_sources_preserved': True}
    protocol = {'schema': SCHEMA, 'settings': config, 'identity': identity,
                'inventory_sha256': canonical_hash(inventory), 'inputs': work['entries'],
                'portable_actors': [{key: model[key] for key in ('id', 'actor_path', 'exported_sha256', 'actor_weights_sha256')}
                                    for model in models.values()],
                'teammate_policy': 'stage-specific fixed_reference or candidate_squad; teammate scripts remain ON',
                'auto_promotion': False}
    protocol['protocol_sha'] = canonical_hash(protocol)
    atomic_json(run / 'inventory.json', inventory)
    atomic_json(run / 'protocol.json', protocol)
    atomic_json(run / 'progress.json', {'status': 'INVENTORIED', 'phase': 'screen',
                'unique_candidates': len(candidate_ids), 'completed_games': 0})
    return protocol


def initialize(name, config, build_dir=None):
    run = run_path(name)
    if run.exists():
        raise FileExistsError('Selector run exists; use resume or a new --run name: ' + str(run))
    torch.set_num_threads(1)
    config = validate_config(config)
    identity = selector_identity(build_dir)
    run.mkdir(parents=True)
    atomic_json(run / 'config.json', {'settings': config, 'identity': identity})
    protocol = finish_inventory(run, config, identity)
    return run, protocol


def verify_run(run, protocol, build_dir=None):
    torch.set_num_threads(1)
    if protocol['identity'] != selector_identity(build_dir):
        raise ValueError('Selector code, native binary or runtime changed; preserve this run and use a new run name')
    expected = {key: value for key, value in protocol.items() if key != 'protocol_sha'}
    if canonical_hash(expected) != protocol['protocol_sha']:
        raise ValueError('Selector protocol was changed')
    inventory = read_json(run / 'inventory.json')
    if canonical_hash(inventory) != protocol['inventory_sha256']:
        raise ValueError('Saved model inventory changed')
    for entry in protocol['inputs']:
        if not Path(entry['path']).is_file() or sha256(entry['path']) != entry['sha256']:
            raise ValueError('Protected model source changed: ' + entry['path'])
    for entry in protocol['portable_actors']:
        if sha256(entry['actor_path']) != entry['exported_sha256']:
            raise ValueError('Private portable actor changed: ' + entry['actor_path'])
    return inventory


def game_descriptor(protocol, candidate, rival, reference, fmt, seed, side, seconds,
                    team_policy='fixed_reference'):
    settings = protocol['settings']
    descriptor = {'candidate_id': candidate, 'rival_id': rival, 'reference_id': reference,
                  'format': list(fmt), 'seed': seed, 'learner_team': side, 'seconds': seconds,
                  'team_policy': team_policy,
                  'learner_scripted_kickoff': settings['learner_scripted_kickoff'],
                  'frozen_scripted_kickoff': True}
    # No stage or candidate-list identity: matching reference games share a cache.
    identity = {'game': descriptor, 'protocol_sha': protocol['protocol_sha'],
                'native': protocol['identity']['native'], 'device': settings['device'],
                'batch_worlds': settings.get('worlds', 8)}
    return {'id': canonical_hash(identity), **descriptor}


def expected_jobs(protocol, inventory, candidate_ids, stage_name, extra_rivals=()):
    cfg = protocol['settings']; stage = cfg['stages'][stage_name]
    roles = inventory['roles']; reference = roles['baseline']
    names = stage.get('rivals', list(cfg['rivals']))
    rivals = list(dict.fromkeys([roles['rival:' + name] for name in names] + list(extra_rivals)))
    candidates = sorted(set(candidate_ids) | {reference})
    team_policy = stage.get('team_policy', 'fixed_reference')
    return [game_descriptor(protocol, candidate, rival,
                            candidate if team_policy == 'candidate_squad' else reference,
                            fmt, seed, side, stage['seconds'], team_policy)
            for candidate in candidates for fmt in stage['formats'] for rival in rivals
            for seed in stage['seeds'] for side in ('blue', 'orange')]


def validate_record(job, record):
    first_goal = job.get('stop_after_first_goal', False)
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in job.items()
                                          if not (first_goal and key == 'seconds')):
        raise ValueError('Cached native game descriptor does not match the frozen protocol')
    if record.get('finish') != 'COMPLETE':
        raise ValueError('Native game did not finish')
    for name in ('goals_for', 'goals_against'):
        if type(record.get(name)) is not int or record[name] < 0:
            raise ValueError('Invalid cached goal count')
    if type(record.get('seconds')) not in (float, int) or not math.isfinite(record['seconds']):
        raise ValueError('Invalid cached match duration')
    if first_goal:
        total = record['goals_for'] + record['goals_against']
        if not 0 < record['seconds'] <= job['seconds'] or total not in (0, 1):
            raise ValueError('Invalid first-goal round')
        if (record.get('round_end') != ('FIRST_GOAL' if total else 'NO_GOAL_TIMEOUT')
                or (not total and abs(record['seconds'] - job['seconds']) > 1 / 120)):
            raise ValueError('First-goal round ended prematurely or has an invalid outcome')
    return record


def cached_records(run, jobs, *, require_complete=False):
    found = []
    missing = []
    registered = read_json(run / 'cache' / 'record_hashes.json', {})
    for job in jobs:
        path = run / 'cache' / 'records' / (job['id'] + '.json')
        if not path.is_file():
            missing.append(job)
        else:
            if job['id'] in registered and sha256(path) != registered[job['id']]:
                raise ValueError('Previously registered cached game changed: ' + str(path))
            found.append(validate_record(job, read_json(path)))
    if require_complete and missing:
        raise ValueError(f'Incomplete selector stage: {len(found)}/{len(jobs)} games')
    return found, missing


def clustered_interval(values, *, alpha=.05):
    array = np.asarray(values, dtype=np.float64)
    if not len(array) or not np.isfinite(array).all():
        raise ValueError('A finite, nonempty seed cluster sample is required')
    if len(array) < 2:
        return {'mean': float(array.mean()), 'lower': None, 'upper': None,
                'independent_seeds': len(array)}
    rng = np.random.default_rng(937)
    means = array[rng.integers(0, len(array), (8000, len(array)))].mean(axis=1)
    return {'mean': float(array.mean()), 'lower': float(np.quantile(means, alpha / 2)),
            'upper': float(np.quantile(means, 1 - alpha / 2)),
            'independent_seeds': len(array)}


def cell_key(row):
    return (tuple(row['format']), row['rival_id'], row['seed'], row['learner_team'], row['seconds'],
            row.get('team_policy', 'fixed_reference'))


def summarize(records, candidate_ids, reference_id, *, comparison_count=1):
    cells = {}
    for row in records:
        key = row['candidate_id'], cell_key(row)
        if key in cells:
            raise ValueError('Duplicate native game in ranking')
        cells[key] = row
    result = []
    for candidate in sorted(set(candidate_ids)):
        rows = [r for r in records if r['candidate_id'] == candidate]
        if not rows:
            continue
        grouped = {}
        modes = {}
        for row in rows:
            reference = cells.get((reference_id, cell_key(row)))
            if reference is None:
                raise ValueError('Ranking requires a matching baseline game for every candidate cell')
            delta = ((row['goals_for'] - row['goals_against'])
                     - (reference['goals_for'] - reference['goals_against'])) * 60 / row['seconds']
            grouped.setdefault(row['seed'], []).append(delta)
            mode = f"{row['format'][0]}v{row['format'][1]}"
            modes.setdefault(mode, {}).setdefault(row['seed'], []).append(delta)
        alpha = .05 / max(1, comparison_count)
        interval = clustered_interval([float(np.mean(v)) for v in grouped.values()], alpha=alpha)
        per_mode = {mode: clustered_interval([float(np.mean(v)) for v in groups.values()], alpha=alpha)
                    for mode, groups in modes.items()}
        result.append({'id': candidate, 'matches': len(rows),
                       'goals_for': sum(r['goals_for'] for r in rows),
                       'goals_against': sum(r['goals_against'] for r in rows),
                       'wins': sum(r['goals_for'] > r['goals_against'] for r in rows),
                       'draws': sum(r['goals_for'] == r['goals_against'] for r in rows),
                       'losses': sum(r['goals_for'] < r['goals_against'] for r in rows),
                       'early_goal_concessions': sum(r.get('early_goal_concessions', 0) for r in rows),
                       'early_goals_for': sum(r.get('early_goals_for', 0) for r in rows),
                       'worst_goals_against_in_one_game': max(r['goals_against'] for r in rows),
                       'worst_paired_seed_mean': min(float(np.mean(v)) for v in grouped.values()),
                       'paired_goal_difference_per_minute': interval, 'per_mode': per_mode,
                       'seed_means': {str(seed): float(np.mean(v)) for seed, v in grouped.items()},
                       'status': 'HELDOUT_POSITIVE' if interval['independent_seeds'] >= 8
                                 and interval['lower'] is not None and interval['lower'] > 0
                                 else 'EXPLORATORY',
                       'interval_alpha': alpha, 'confirmed_best': False})
    return sorted(result, key=lambda row: (-row['paired_goal_difference_per_minute']['mean'],
                                          -row['wins'], row['goals_against'], row['id']))


def leaders_with_ties(rows, count, metric=None):
    if not rows:
        return []
    metric = metric or (lambda row: row['paired_goal_difference_per_minute']['mean'])
    ordered = sorted(rows, key=lambda row: (-metric(row), row['id']))
    cutoff = metric(ordered[min(count, len(ordered)) - 1])
    return [row for index, row in enumerate(ordered)
            if index < count or math.isclose(metric(row), cutoff, rel_tol=1e-12, abs_tol=1e-12)]


def shortlist(ranking, inventory, count, uncertain_extra=0, include_specialists=False):
    """Retain ties/borderline evidence and anchors, never delete losing models."""
    families = sorted({family for model in inventory['models'].values() for family in model['families']})
    top = {}
    specialists = {}
    ties = {}
    selected = set(inventory['protected_ids'])
    for family in families:
        rows = [row for row in ranking if family in inventory['models'][row['id']]['families']]
        leaders = leaders_with_ties(rows, count)
        family_ids = [row['id'] for row in leaders]
        top[family] = family_ids
        ties[family] = family_ids[count:] if len(family_ids) > count else []
        selected.update(family_ids)
        if rows and len(rows) >= count and uncertain_extra:
            cutoff = rows[min(count, len(rows)) - 1]['paired_goal_difference_per_minute']
            lower = cutoff['lower']
            uncertain = [row for row in rows if row['id'] not in family_ids
                         if lower is None or row['paired_goal_difference_per_minute']['upper'] is None
                         or row['paired_goal_difference_per_minute']['upper'] >= lower]
            selected.update(row['id'] for row in uncertain[:uncertain_extra])
        if include_specialists:
            modes = sorted({mode for row in rows for mode in row['per_mode']})
            specialists[family] = {}
            for mode in modes:
                available = [row for row in rows if mode in row['per_mode']]
                mode_leaders = leaders_with_ties(available, 1, lambda row: row['per_mode'][mode]['mean'])
                specialists[family][mode] = [row['id'] for row in mode_leaders]
                selected.update(row['id'] for row in mode_leaders)
    return {'candidate_ids': sorted(selected), 'top_per_family': top, 'specialists': specialists,
            'protected_ids': inventory['protected_ids'], 'provisional': True,
            'requested_per_family': count, 'tied_at_cutoff': ties,
            'unresolved_exact_ties': any(ties.values()),
            'all_sources_preserved': True}


def build_stage(run, protocol, inventory, name):
    cfg = protocol['settings']
    extra_rivals = []
    if name == 'screen':
        candidates = sorted(set(inventory['candidate_ids']) | set(inventory['protected_ids']))
    else:
        previous = read_json(run / 'stages' / STAGES[STAGES.index(name) - 1] / 'ranking.json')
        if not previous or previous.get('complete') is not True:
            raise ValueError('Previous selector stage must finish before constructing ' + name)
        ranking = previous['ranking']
        if name == 'refine':
            chosen = shortlist(ranking, inventory, cfg['refine_per_family'], cfg['uncertain_extra_per_family'])
        elif name == 'finalists':
            chosen = shortlist(ranking, inventory, cfg['top_per_family'], include_specialists=True)
            heads = cfg['stages'][name].get('head_to_head_per_family', 0)
            for ids in chosen['top_per_family'].values():
                extra_rivals.extend(ids[:heads])
        else:
            overall = leaders_with_ties(ranking, cfg['confirm_leaders'])
            candidates = {row['id'] for row in overall} | set(inventory['protected_ids'])
            for mode in {mode for row in ranking for mode in row['per_mode']}:
                available = [row for row in ranking if mode in row['per_mode']]
                candidates.update(row['id'] for row in leaders_with_ties(
                    available, 1, lambda row: row['per_mode'][mode]['mean']))
            chosen = {'candidate_ids': sorted(candidates)}
        candidates = chosen['candidate_ids']
    return {'stage': name, 'candidate_ids': candidates,
            'jobs': expected_jobs(protocol, inventory, candidates, name, extra_rivals)}


def stage_ranking(run, protocol, inventory, plan):
    records, missing = cached_records(run, plan['jobs'])
    # Partial groups can lack their baseline game: rank only complete candidates.
    reference = inventory['roles']['baseline']
    expected = {}
    actual = {}
    for job in plan['jobs']:
        expected.setdefault(job['candidate_id'], set()).add(job['id'])
    for row in records:
        actual.setdefault(row['candidate_id'], set()).add(row['id'])
    complete_ids = [id for id in expected if actual.get(id, set()) == expected[id]]
    if reference not in complete_ids:
        ranking = []
    else:
        available = [row for row in records if row['candidate_id'] in complete_ids]
        comparisons = len(plan['candidate_ids']) * len(protocol['settings']['stages'][plan['stage']]['formats'])
        ranking = summarize(available, complete_ids, reference, comparison_count=comparisons)
    short = shortlist(ranking, inventory, protocol['settings']['top_per_family'], include_specialists=True)
    document = {'stage': plan['stage'], 'complete': not missing, 'ranking': ranking,
                'team_policy': protocol['settings']['stages'][plan['stage']].get('team_policy', 'fixed_reference'),
                'shortlist': short, 'completed_games': len(records), 'total_games': len(plan['jobs']),
                'tied_leader_ids': [row['id'] for row in leaders_with_ties(ranking, 1)],
                'all_sources_preserved': True, 'auto_promotion': False,
                'note': 'Seed-cluster bootstrap intervals use a conservative comparison-count adjustment. '
                        'Small seed samples and team scores with scripted frozen-policy teammates are exploratory; '
                        'no report guarantees the best policy or a competitive rank.'}
    atomic_json(run / 'stages' / plan['stage'] / 'ranking.json', document)
    return document


def native_manifest(run, protocol, inventory, jobs):
    needed = {id for job in jobs for id in (job['candidate_id'], job['rival_id'], job['reference_id'])}
    actors = [{'id': id, 'path': inventory['models'][id]['actor_path'],
               'sha256': inventory['models'][id]['exported_sha256']} for id in sorted(needed)]
    return {'schema': SCHEMA, 'protocol_sha': protocol['protocol_sha'], 'actors': actors,
            'jobs': jobs, 'reference_id': inventory['roles']['baseline'],
            'cache_dir': str((run / 'cache' / 'records').resolve())}


def execute_group(run, protocol, inventory, stage, jobs, build_dir=None):
    folder = run / 'stages' / stage / 'groups' / canonical_hash([job['id'] for job in jobs])[:20]
    folder.mkdir(parents=True, exist_ok=True)
    # The native contract requires baseline games in each request. Completed
    # paired baseline games are supplied too and reused without new simulation.
    reference = inventory['roles']['baseline']
    group_jobs = {job['id']: job for job in jobs}
    for job in jobs:
        paired = game_descriptor(protocol, reference, job['rival_id'], reference, job['format'],
                                 job['seed'], job['learner_team'], job['seconds'],
                                 job.get('team_policy', 'fixed_reference'))
        group_jobs.setdefault(paired['id'], paired)
    manifest = native_manifest(run, protocol, inventory, list(group_jobs.values()))
    atomic_json(folder / 'manifest.json', manifest)
    command = [native.binary_path(build_dir), '--mode', 'selector-eval', '--eval-manifest',
               folder / 'manifest.json', '--out', folder, '--meshes', native.helper.meshes(),
               '--device', protocol['settings']['device'], '--pause', run / 'PAUSE',
               '--eval-worlds', protocol['settings']['worlds']]
    result = native.checked_process(command, folder / f'eval_{time.time_ns()}.log',
                                    marker='SLATER_SELECTOR_COMPLETE', pause=run / 'PAUSE')
    registry_path = run / 'cache' / 'record_hashes.json'
    registered = read_json(registry_path, {})
    for job in group_jobs.values():
        path = run / 'cache' / 'records' / (job['id'] + '.json')
        if path.is_file():
            validate_record(job, read_json(path))
            digest = sha256(path)
            if job['id'] in registered and registered[job['id']] != digest:
                raise ValueError('Previously registered cached game changed: ' + str(path))
            registered[job['id']] = digest
    atomic_json(registry_path, registered)
    return result


def write_selection(run, protocol, inventory, document):
    if not document['ranking']:
        return
    previous = read_json(run / 'selection.json')
    if previous and STAGES.index(previous['stage']) > STAGES.index(document['stage']):
        return  # Resume may revisit completed earlier stages; retain later evidence.
    leader = document['ranking'][0]
    model = inventory['models'][leader['id']]
    primary = next((source for source in model['source_paths'] if source['families']), model['source_paths'][0])
    selection = {'schema': SCHEMA, 'checkpoint': primary['path'], 'source': primary['path'],
                 'experiment_source': model['actor_path'], 'actor_path': model['actor_path'],
                 'exported_sha256': model['exported_sha256'],
                 'actor_weights_sha256': model['actor_weights_sha256'], 'model_id': model['id'],
                 'source_paths': model['source_paths'], 'families': model['families'],
                 'protocol_sha': protocol['protocol_sha'], 'selection_run': str(run.resolve()),
                 'stage': document['stage'], 'stage_complete': document['complete'],
                 'team_policy': document.get('team_policy', 'fixed_reference'),
                 'status': leader['status'], 'evidence': leader,
                 'tied_leader_ids': document.get('tied_leader_ids', [leader['id']]),
                 'playing_model': protocol['settings']['baseline'], 'auto_promotion': False,
                 'confirmed_best': False,
                 'protected_baselines': [inventory['models'][id] for id in inventory['protected_ids']],
                 'note': 'This source is suitable for an isolated training experiment. '
                         'It does not automatically replace the protected playing model.'}
    atomic_json(run / 'selection.json', selection)
    atomic_json(run / 'shortlist.json', {**document['shortlist'], 'stage': document['stage'],
                'team_policy': document.get('team_policy', 'fixed_reference'),
                'models': {id: inventory['models'][id] for id in document['shortlist']['candidate_ids']},
                'per_mode_rankings': {mode: sorted([row for row in document['ranking'] if mode in row['per_mode']],
                                      key=lambda row: -row['per_mode'][mode]['mean'])
                                     for mode in {mode for row in document['ranking'] for mode in row['per_mode']}}})
    lines = ['# Checkpoint shortlist', '', 'Exploratory simulator results; all source checkpoints are preserved.',
             '', f"Stage: {document['stage']} ({document['completed_games']}/{document['total_games']} games).",
             '', '| Rank | Sources | Paired goal difference/minute vs reference | Independent seeds |',
             '| --- | --- | ---: | ---: |']
    for index, row in enumerate(document['ranking'][:20], 1):
        sources = '; '.join(Path(source['path']).name for source in inventory['models'][row['id']]['source_paths']
                            if source['families']) or Path(inventory['models'][row['id']]['source_paths'][0]['path']).name
        score = row['paired_goal_difference_per_minute']
        lines.append(f"| {index} | {sources} | {score['mean']:.3f} | {score['independent_seeds']} |")
    scope = ('Team games evaluate one candidate-controlled car with fixed reference teammates.'
             if document.get('team_policy', 'fixed_reference') == 'fixed_reference' else
             'Team games use the candidate policy for its whole squad; the selected car learns its kickoff '
             'and its frozen-policy teammates retain scripted kickoff.')
    lines += ['', scope + ' A team goal is not proof that one particular car performed the mechanic.', '',
              'Full paths, aliases, per-mode leaders and confidence intervals are in shortlist.json and stage ranking.json.', '']
    (run / 'SHORTLIST.md').write_text('\n'.join(lines), encoding='utf-8')


def run_campaign(name, *, config=None, build_dir=None, resume=False, max_games=None, until='confirm'):
    if until not in STAGES:
        raise ValueError('Unknown final selector stage')
    if max_games is not None and (type(max_games) is not int or not 1 <= max_games <= 100000):
        raise ValueError('max_games must be a bounded positive integer')
    run = run_path(name)
    torch.set_num_threads(1)
    with process_lock(BASE / 'locks' / (name + '.lock')):
        if resume:
            saved = read_json(run / 'config.json')
            if not saved:
                raise ValueError('No selector run is available to resume')
            if saved['identity'] != selector_identity(build_dir):
                raise ValueError('Selector runtime or code changed; choose a new run name')
            if config is not None and validate_config(config) != saved['settings']:
                raise ValueError('Resume does not allow changed selector settings')
            (run / 'PAUSE').unlink(missing_ok=True)
            protocol = read_json(run / 'protocol.json') or finish_inventory(run, saved['settings'], saved['identity'])
        else:
            run, protocol = initialize(name, config or DEFAULT, build_dir)
        if protocol is None:
            return read_json(run / 'progress.json')
        inventory = verify_run(run, protocol, build_dir)
        consumed = 0
        for stage in STAGES[:STAGES.index(until) + 1]:
            plan_path = run / 'stages' / stage / 'plan.json'
            plan = read_json(plan_path) or build_stage(run, protocol, inventory, stage)
            atomic_json(plan_path, plan)
            while True:
                records, missing = cached_records(run, plan['jobs'])
                status = 'PAUSED' if (run / 'PAUSE').exists() else 'GAME_BUDGET_REACHED' if max_games is not None and consumed >= max_games else None
                atomic_json(run / 'progress.json', {'status': status or 'EVALUATING', 'phase': stage,
                            'completed_games': len(records), 'total_games': len(plan['jobs']),
                            'games_this_invocation': consumed, 'protocol_sha': protocol['protocol_sha']})
                if not missing:
                    report = stage_ranking(run, protocol, inventory, plan)
                    write_selection(run, protocol, inventory, report)
                    break
                if status:
                    report = stage_ranking(run, protocol, inventory, plan)
                    write_selection(run, protocol, inventory, report)
                    verify_run(run, protocol, build_dir)
                    return read_json(run / 'progress.json')
                # Baseline games first, so partial results remain meaningfully paired.
                reference = inventory['roles']['baseline']
                missing.sort(key=lambda job: (job['candidate_id'] != reference, job['candidate_id'], job['id']))
                size = protocol['settings']['job_group']
                if max_games is not None:
                    size = min(size, max_games - consumed)
                group = missing[:size]
                before = len(records)
                execute_group(run, protocol, inventory, stage, group, build_dir)
                after, _ = cached_records(run, plan['jobs'])
                gained = len(after) - before
                consumed += gained
                if not gained and not (run / 'PAUSE').exists():
                    raise RuntimeError('Native selector returned without completing a cached game')
                stage_ranking(run, protocol, inventory, plan)
        verify_run(run, protocol, build_dir)
        result = {'status': 'FINITE_SELECTION_COMPLETE', 'phase': until,
                  'games_this_invocation': consumed, 'selection': str(run / 'selection.json'),
                  'shortlist': str(run / 'SHORTLIST.md'), 'all_sources_preserved': True,
                  'auto_promotion': False}
        atomic_json(run / 'progress.json', result)
        return result


def parse_map(values):
    result = {}
    for text in values:
        if '=' not in text:
            raise ValueError('Use NAME=PATH or NAME=GLOB')
        name, value = text.split('=', 1)
        if not name or not value:
            raise ValueError('Use a nonempty NAME=PATH or NAME=GLOB')
        result[name] = value
    return result


def main():
    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'run', 'resume', 'pause', 'status', 'rank'))
    parser.add_argument('--run', required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--anchor', action='append', default=[])
    parser.add_argument('--rival', action='append', default=[])
    parser.add_argument('--family', action='append', default=[])
    parser.add_argument('--device', choices=('cpu', 'cuda', 'auto'))
    parser.add_argument('--worlds', type=int)
    parser.add_argument('--max-games', type=int)
    parser.add_argument('--until', choices=STAGES, default='confirm')
    args = parser.parse_args()
    run = run_path(args.run)
    saved_settings = read_json(run / 'config.json', {}).get('settings', {})
    requested = read_json(args.config) if args.config else {}
    goal_settings = requested.get('goal_race', saved_settings.get('goal_race'))
    if goal_settings is not None and args.command in ('run', 'resume', 'rank'):
        from slater_nexto_goal_benchmark import run_benchmark, rebuild_report
        if args.command == 'rank':
            result = rebuild_report(run, args.build_dir)
        else:
            result = run_benchmark(args.run,
                config=merge_config(DEFAULT, requested) if args.command == 'run' else None,
                build_dir=args.build_dir, resume=args.command == 'resume', max_games=args.max_games)
        summary = {key: result[key] for key in ('status', 'phase', 'complete', 'completed_games',
                   'completed_model_formats', 'total_model_formats') if key in result}
        summary['report'] = str(run / 'goal_benchmark.json')
        print('MODEL_SELECTION_COMPLETE', json.dumps(summary), flush=True)
        return
    if args.command == 'pause':
        if not (run / 'config.json').is_file():
            raise ValueError('No selector run is available to pause')
        (run / 'PAUSE').touch()
        print('Pause requested; completed native games remain cached.'); return
    if args.command == 'status':
        print(json.dumps(read_json(run / 'progress.json', {'status': 'NOT_FOUND'}), indent=2)); return
    if args.command == 'rank':
        protocol = read_json(run / 'protocol.json')
        if not protocol:
            raise ValueError('Inventory must complete before ranking')
        inventory = verify_run(run, protocol, args.build_dir)
        reports = []
        for stage in STAGES:
            plan = read_json(run / 'stages' / stage / 'plan.json')
            if plan:
                report = stage_ranking(run, protocol, inventory, plan); reports.append(report)
                if report['complete']:
                    write_selection(run, protocol, inventory, report)
        print(json.dumps({'reports': [{key: report[key] for key in ('stage', 'complete', 'completed_games', 'total_games')}
                                      for report in reports], 'selection': read_json(run / 'selection.json')}, indent=2)); return
    changes = read_json(args.config) if args.config else {}
    for key in ('baseline', 'device', 'worlds'):
        if getattr(args, key) is not None:
            changes[key] = str(getattr(args, key)) if key == 'baseline' else getattr(args, key)
    for key, values in (('anchors', args.anchor), ('rivals', args.rival), ('families', args.family)):
        if values:
            changes[key] = parse_map(values)
    config = merge_config(DEFAULT, changes)
    # An explicit rival pool also replaces screen names; never invent absent rivals.
    if 'rivals' in changes and 'rivals' not in changes.get('stages', {}).get('screen', {}):
        config['stages']['screen']['rivals'] = list(config['rivals'])[:2]
    if args.command == 'inventory':
        with process_lock(BASE / 'locks' / (args.run + '.lock')):
            run, protocol = initialize(args.run, config, args.build_dir)
        print(json.dumps({'inventory': str(run / 'inventory.json'), 'status': 'INVENTORIED' if protocol else 'PAUSED'}, indent=2))
    else:
        changed = bool(changes)
        result = run_campaign(args.run, config=config if args.command == 'run' or changed else None,
                              build_dir=args.build_dir, resume=args.command == 'resume',
                              max_games=args.max_games, until=args.until)
        print('MODEL_SELECTION_COMPLETE', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
