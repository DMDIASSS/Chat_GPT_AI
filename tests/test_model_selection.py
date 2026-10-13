import json
from pathlib import Path

import pytest
import torch

import slater_model_selection as selector


def tiny_config(tmp_path, actor):
    changes = {'baseline': str(actor), 'anchors': {'fixture': str(actor)},
               'rivals': {'fixture': str(actor)}, 'families': {'mechanics': [str(tmp_path / 'models' / '*.pt')]},
               'device': 'cpu', 'worlds': 2, 'job_group': 3, 'top_per_family': 1,
               'refine_per_family': 1, 'uncertain_extra_per_family': 1, 'confirm_leaders': 1,
               'stages': {name: {'seeds': [1000 + index * 100, 1001 + index * 100],
                                  'seconds': .1, 'formats': ['1v1'], 'rivals': ['fixture'],
                                  'head_to_head_per_family': 0}
                          for index, name in enumerate(selector.STAGES)}}
    return selector.merge_config(selector.DEFAULT, changes)


@pytest.fixture
def actor_files(tmp_path):
    torch.set_num_threads(1)
    actor = selector.load_actor(selector.ROOT, selector.native.DEFAULT_RIVAL)
    models = tmp_path / 'models'
    models.mkdir()
    state = {key: value.clone() for key, value in actor.state_dict().items()}
    first = models / 'update_000180.pt'
    alias = models / 'accepted_000180.pt'
    second = models / 'update_000278.pt'
    torch.save({'actor': state, 'updates': 180}, first)
    torch.save({'actor': state, 'updates': 180, 'different_critic': torch.ones(3)}, alias)
    changed = {key: value.clone() for key, value in state.items()}
    changed[next(iter(changed))].reshape(-1)[0] += .01
    torch.save({'actor': changed, 'updates': 278}, second)
    return first, alias, second


def test_default_inventory_includes_accepted_aliases_and_formats():
    assert any('accepted' in pattern for pattern in selector.DEFAULT['families']['mechanics'])
    cfg = selector.validate_config(selector.DEFAULT)
    assert cfg['stages']['screen']['formats'] == [[1, 1]]
    assert cfg['stages']['refine']['formats'] == [[1, 1], [2, 2], [3, 3]]
    invalid = selector.merge_config(selector.DEFAULT, {'stages': {'confirm': {'seeds': [730000000]}}})
    with pytest.raises(ValueError, match='distinct independent'):
        selector.validate_config(invalid)
    with pytest.raises(ValueError, match='ASCII'):
        selector.run_path('../escape')


def test_inventory_deduplicates_real_weights_and_preserves_aliases(tmp_path, actor_files, monkeypatch):
    first, alias, second = actor_files
    run = tmp_path / 'run'
    monkeypatch.setattr(selector, 'run_path', lambda name: run)
    identity = {'native': {'binary_sha256': 'fixture'}, 'runtime': {}, 'code': {}}
    monkeypatch.setattr(selector, 'selector_identity', lambda build=None: identity)
    cfg = tiny_config(tmp_path, first)
    cfg['families']['team'] = [str(alias)]
    before = {str(path): selector.sha256(path) for path in actor_files}
    run, protocol = selector.initialize('fixture', cfg)
    inventory = selector.read_json(run / 'inventory.json')
    assert inventory['source_files'] == 3
    assert inventory['distinct_candidates'] == 2
    assert inventory['aliases'] == 1
    baseline = inventory['models'][inventory['roles']['baseline']]
    assert baseline['families'] == ['mechanics', 'team']
    assert {Path(entry['path']).name for entry in baseline['source_paths']} == {first.name, alias.name}
    assert len(list((run / 'actors').glob('*.pt'))) == 2
    assert selector.verify_run(run, protocol)['all_sources_preserved']
    assert before == {str(path): selector.sha256(path) for path in actor_files}


def test_unsupported_family_checkpoints_are_reported_not_selected(tmp_path, actor_files, monkeypatch):
    first = actor_files[0]
    bad = tmp_path / 'models' / 'unsupported.pt'
    torch.save({'actor': {'wrong': torch.ones(2)}}, bad)
    run = tmp_path / 'run'
    monkeypatch.setattr(selector, 'run_path', lambda name: run)
    monkeypatch.setattr(selector, 'selector_identity', lambda build=None: {})
    selector.initialize('fixture', tiny_config(tmp_path, first))
    inventory = selector.read_json(run / 'inventory.json')
    assert any(entry['path'] == str(bad) for entry in inventory['rejected'])
    assert all(str(bad) not in {entry['path'] for entry in model['source_paths']}
               for model in inventory['models'].values())


def test_native_inventory_requires_complete_marker_and_all_components(tmp_path):
    checkpoints = tmp_path / 'native'
    complete = checkpoints / 'checkpoint_000001'
    partial = checkpoints / 'checkpoint_000002'
    complete.mkdir(parents=True)
    partial.mkdir()
    for name in selector.native.CHECKPOINT_FILES:
        (complete / name).write_bytes(b'complete')
        (partial / name).write_bytes(b'partial')
    (complete / 'COMPLETE').write_text('ok')
    cfg = selector.merge_config(selector.DEFAULT, {'families': {'attention': [str(checkpoints / 'checkpoint_*')]}})
    sources, skipped = selector.discovered_sources(cfg)
    assert any(entry['path'] == str(complete / 'actor.pt') for entry in sources)
    assert all(entry['path'] != str(partial / 'actor.pt') for entry in sources)
    assert any(entry['path'] == str(partial) for entry in skipped)


def protocol_fixture():
    return {'settings': {'device': 'cpu', 'learner_scripted_kickoff': False},
            'protocol_sha': 'frozen-run', 'identity': {'native': {'binary_sha256': 'build'}}}


def completed_record(job, goals_for=0, goals_against=0):
    return {**job, 'finish': 'COMPLETE', 'goals_for': goals_for, 'goals_against': goals_against}


def test_game_cache_identity_changes_with_policy_backend_and_settings():
    protocol = protocol_fixture()
    a = selector.game_descriptor(protocol, 'candidate', 'rival', 'reference', [1, 1], 12, 'blue', 30.)
    assert a == selector.game_descriptor(protocol, 'candidate', 'rival', 'reference', [1, 1], 12, 'blue', 30.)
    assert a['id'] != selector.game_descriptor(protocol, 'other', 'rival', 'reference', [1, 1], 12, 'blue', 30.)['id']
    protocol['identity']['native']['binary_sha256'] = 'new-build'
    assert a['id'] != selector.game_descriptor(protocol, 'candidate', 'rival', 'reference', [1, 1], 12, 'blue', 30.)['id']


def test_cache_rejects_tampered_game_or_unfinished_record(tmp_path):
    job = selector.game_descriptor(protocol_fixture(), 'candidate', 'rival', 'reference', [1, 1], 12, 'blue', 30.)
    path = tmp_path / 'cache' / 'records' / (job['id'] + '.json')
    selector.atomic_json(path, completed_record(job, 2, 1))
    rows, missing = selector.cached_records(tmp_path, [job], require_complete=True)
    assert rows[0]['goals_for'] == 2 and not missing
    selector.atomic_json(path, {**completed_record(job), 'seed': 13})
    with pytest.raises(ValueError, match='descriptor'):
        selector.cached_records(tmp_path, [job])
    selector.atomic_json(path, {**completed_record(job), 'finish': 'PARTIAL'})
    with pytest.raises(ValueError, match='did not finish'):
        selector.cached_records(tmp_path, [job])


def test_registered_cache_detects_edits_to_goal_counts(tmp_path):
    job = selector.game_descriptor(protocol_fixture(), 'candidate', 'rival', 'reference', [1, 1], 12, 'blue', 30.)
    path = tmp_path / 'cache' / 'records' / (job['id'] + '.json')
    selector.atomic_json(path, completed_record(job, 1, 0))
    selector.atomic_json(tmp_path / 'cache' / 'record_hashes.json', {job['id']: selector.sha256(path)})
    selector.atomic_json(path, completed_record(job, 2, 0))
    with pytest.raises(ValueError, match='registered cached game changed'):
        selector.cached_records(tmp_path, [job])


def test_ranking_pairs_reference_and_clusters_colors_by_seed():
    records = []
    protocol = protocol_fixture()
    for seed in (10, 20):
        for side in ('blue', 'orange'):
            reference = selector.game_descriptor(protocol, 'reference', 'rival', 'reference', [1, 1], seed, side, 30.)
            candidate = selector.game_descriptor(protocol, 'candidate', 'rival', 'reference', [1, 1], seed, side, 30.)
            records += [completed_record(reference, 1, 1), completed_record(candidate, 2, 1)]
    result = selector.summarize(records, ['candidate', 'reference'], 'reference')
    assert result[0]['id'] == 'candidate'
    score = result[0]['paired_goal_difference_per_minute']
    assert score['mean'] == 2 and score['independent_seeds'] == 2
    assert result[0]['confirmed_best'] is False
    with pytest.raises(ValueError, match='matching baseline'):
        selector.summarize([r for r in records if r['candidate_id'] != 'reference'], ['candidate'], 'reference')


def test_single_seed_has_no_confidence_interval():
    result = selector.clustered_interval([7.])
    assert result == {'mean': 7., 'lower': None, 'upper': None, 'independent_seeds': 1}


def test_shortlist_preserves_anchors_uncertain_neighbors_and_specialists():
    inventory = {'models': {name: {'families': ['mechanics']} for name in ('leader', 'second', 'specialist', 'anchor')},
                 'protected_ids': ['anchor']}
    ranking = [{'id': name, 'paired_goal_difference_per_minute': {'mean': mean, 'lower': lower, 'upper': upper},
                'per_mode': {'1v1': {'mean': mean}, '3v3': {'mean': team}}}
               for name, mean, lower, upper, team in (('leader', 2., 0., 4., 0.),
                                                      ('second', 1., -1., 3., 0.),
                                                      ('specialist', -.5, -2., 1., 3.),
                                                      ('anchor', -1., -3., 0., -1.))]
    short = selector.shortlist(ranking, inventory, 1, uncertain_extra=1, include_specialists=True)
    assert short['top_per_family']['mechanics'] == ['leader']
    assert short['candidate_ids'] == ['anchor', 'leader', 'second', 'specialist']
    assert short['specialists']['mechanics']['3v3'] == ['specialist']


def test_exact_screen_ties_are_retained_instead_of_hash_eliminated():
    names = [f'model_{i:03}' for i in range(40)]
    inventory = {'models': {name: {'families': ['mechanics']} for name in names}, 'protected_ids': []}
    ranking = [{'id': name, 'paired_goal_difference_per_minute': {'mean': 0., 'lower': None, 'upper': None},
                'per_mode': {'1v1': {'mean': 0.}}} for name in names]
    result = selector.shortlist(ranking, inventory, 8, uncertain_extra=4)
    assert result['candidate_ids'] == names
    assert result['unresolved_exact_ties'] is True
    assert len(result['tied_at_cutoff']['mechanics']) == 32
    assert len(selector.leaders_with_ties(ranking, 4)) == 40


def test_reference_games_are_reused_across_candidate_groups():
    cfg = selector.validate_config(selector.DEFAULT)
    protocol = {**protocol_fixture(), 'settings': cfg}
    inventory = {'roles': {'baseline': 'baseline', 'rival:nexto': 'nexto', 'rival:update180': 'baseline',
                           'rival:update278': '278'}}
    first = selector.expected_jobs(protocol, inventory, ['one'], 'screen')
    second = selector.expected_jobs(protocol, inventory, ['two'], 'screen')
    a = {job['id'] for job in first if job['candidate_id'] == 'baseline'}
    b = {job['id'] for job in second if job['candidate_id'] == 'baseline'}
    assert a == b and len(a) == 4


def test_candidate_squad_uses_same_actor_teammates_and_matched_baseline():
    cfg = selector.validate_config(selector.DEFAULT)
    protocol = {**protocol_fixture(), 'settings': cfg}
    inventory = {'roles': {'baseline': 'baseline', 'rival:nexto': 'nexto', 'rival:update180': 'baseline',
                           'rival:update278': '278'}}
    jobs = selector.expected_jobs(protocol, inventory, ['candidate'], 'confirm')
    assert all(job['reference_id'] == job['candidate_id'] for job in jobs)
    assert all(job['team_policy'] == 'candidate_squad' for job in jobs)
    assert all(job['frozen_scripted_kickoff'] is True and job['learner_scripted_kickoff'] is False for job in jobs)
    reference = {selector.cell_key(job) for job in jobs if job['candidate_id'] == 'baseline'}
    assert reference == {selector.cell_key(job) for job in jobs if job['candidate_id'] == 'candidate'}
    contribution = selector.expected_jobs(protocol, inventory, ['candidate'], 'refine')
    assert all(job['reference_id'] == 'baseline' and job['team_policy'] == 'fixed_reference' for job in contribution)


def test_real_inventory_budget_pause_and_resume_does_not_replay_completed_games(tmp_path, actor_files, monkeypatch):
    first = actor_files[0]
    run = tmp_path / 'run'
    monkeypatch.setattr(selector, 'BASE', tmp_path / 'selector')
    monkeypatch.setattr(selector, 'run_path', lambda name: run)
    monkeypatch.setattr(selector, 'selector_identity', lambda build=None: {'native': {'binary_sha256': 'fixture'}})
    calls = []
    def evaluator(run, protocol, inventory, stage, jobs, build_dir=None):
        for job in jobs:
            assert not (run / 'cache' / 'records' / (job['id'] + '.json')).exists()
            calls.append(job['id'])
            selector.atomic_json(run / 'cache' / 'records' / (job['id'] + '.json'), completed_record(job))
        return {'status': 'COMPLETE'}
    monkeypatch.setattr(selector, 'execute_group', evaluator)
    result = selector.run_campaign('fixture', config=tiny_config(tmp_path, first), max_games=3, until='screen')
    assert result['status'] == 'GAME_BUDGET_REACHED' and len(calls) == 3
    (run / 'PAUSE').touch()
    result = selector.run_campaign('fixture', resume=True, until='screen')
    assert result['status'] == 'FINITE_SELECTION_COMPLETE' and len(calls) == len(set(calls))
    selection = selector.read_json(run / 'selection.json')
    assert Path(selection['actor_path']).is_file()
    assert selection['auto_promotion'] is False
    assert selection['playing_model'] == str(first)
    assert selection['status'] == 'EXPLORATORY'
    original_calls = list(calls)
    selector.run_campaign('fixture', resume=True, until='screen')
    assert calls == original_calls
    first.write_bytes(first.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Protected model source changed'):
        selector.run_campaign('fixture', resume=True, until='screen')


def test_resume_rejects_changed_runtime_before_evaluation(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    run.mkdir()
    monkeypatch.setattr(selector, 'BASE', tmp_path)
    monkeypatch.setattr(selector, 'run_path', lambda name: run)
    selector.atomic_json(run / 'config.json', {'settings': {}, 'identity': {'native': 'old'}})
    monkeypatch.setattr(selector, 'selector_identity', lambda build=None: {'native': 'new'})
    with pytest.raises(ValueError, match='runtime or code changed'):
        selector.run_campaign('fixture', resume=True)
