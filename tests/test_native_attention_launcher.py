import json
from pathlib import Path
import sys

import pytest

import slater_native_attention as launcher


@pytest.mark.parametrize('arguments, expected', [([], 'cpu'), (['--device', 'cpu'], 'cpu'),
                                                (['--device', 'cuda'], 'cuda')])
def test_parity_device_is_explicit_and_defaults_to_cpu(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setattr(launcher, 'parity', lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, 'argv', ['slater_native_attention.py', 'parity', *arguments])
    launcher.main()
    assert calls[0]['device'] == expected


def test_run_names_and_bounded_profiles():
    for name in ('../other', '', 'space name', 'a/b', 'а'):
        with pytest.raises(ValueError):
            launcher.run_path(name)
    assert launcher.run_path('attention_01').name == 'attention_01'
    assert launcher.validate_profile(launcher.PROFILE)['games'] == 8
    for key, value in [('games', True), ('steps', 0), ('actor_lr', float('nan')),
                       ('teacher_weight', -1), ('device', 'other')]:
        with pytest.raises(ValueError):
            launcher.validate_profile({**launcher.PROFILE, key: value})


def test_missing_source_never_falls_back_to_nexto(tmp_path):
    with pytest.raises(FileNotFoundError, match='no automatic Nexto fallback'):
        launcher.validate_source(tmp_path / 'missing_update180.pt')


def test_complete_checkpoints_require_every_resume_component(tmp_path):
    root = tmp_path / 'run'
    checkpoints = root / 'checkpoints'
    complete = checkpoints / 'checkpoint_000002'
    partial = checkpoints / 'checkpoint_000003'
    complete.mkdir(parents=True)
    partial.mkdir()
    for name in launcher.CHECKPOINT_FILES:
        (complete / name).write_text('{}')
        (partial / name).write_text('{}')
    (complete / 'COMPLETE.json').write_text('{}')
    assert launcher.latest_checkpoint(root) == complete.resolve()
    with pytest.raises(ValueError, match='Incomplete'):
        launcher.complete_checkpoint(partial)
    (complete / 'rng.pt').unlink()
    with pytest.raises(ValueError, match='rng.pt'):
        launcher.complete_checkpoint(complete)


def test_zero_exit_without_verified_native_marker_is_rejected():
    with pytest.raises(RuntimeError, match='zero exit code is insufficient'):
        launcher.marker_json('process finished\n', 'SLATER_ATTENTION_COMPLETE')
    result = launcher.marker_json('noise\nSLATER_ATTENTION_COMPLETE {"updates":2,"decisions":64}\n',
                                  'SLATER_ATTENTION_COMPLETE')
    assert result == {'updates': 2, 'decisions': 64}
    with pytest.raises(RuntimeError, match='Malformed'):
        launcher.marker_json('SLATER_ATTENTION_COMPLETE {broken}', 'SLATER_ATTENTION_COMPLETE')
    with pytest.raises(RuntimeError, match='Nonfinite'):
        launcher.marker_json('SLATER_ATTENTION_COMPLETE {"timings":{"rate":NaN}}',
                             'SLATER_ATTENTION_COMPLETE')


def test_build_or_runtime_change_refuses_resume(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    run.mkdir()
    monkeypatch.setattr(launcher, 'run_path', lambda name: run)
    monkeypatch.setattr(launcher, 'binary_identity', lambda build: {'binary_sha256': 'new'})
    monkeypatch.setattr(launcher, 'code_identity', lambda: {})
    (run / 'protocol.json').write_text(json.dumps({'native': {'binary_sha256': 'old'}, 'code': {}}))
    with pytest.raises(ValueError, match='changed'):
        launcher.check_run('run')


def test_protected_source_change_is_detected(tmp_path):
    source = tmp_path / 'source.pt'
    source.write_bytes(b'original')
    entry = {'path': str(source), 'sha256': launcher.sha256(source)}
    protocol = {key: entry for key in ('source', 'teacher_source', 'rival_source')}
    launcher.verify_protected(protocol)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Protected source changed'):
        launcher.verify_protected(protocol)


def test_export_preserves_all_original_attention_actor_weights(tmp_path):
    original = launcher.DEFAULT_RIVAL
    before = launcher.sha256(original)
    exported = tmp_path / 'private.pt'
    report = launcher.export_actor(original, exported)
    assert report['actor_weights_identical']
    assert report['actor_tensors'] == 44
    assert report['actor_parameters'] == 444032
    assert launcher.sha256(original) == before
    with pytest.raises(FileExistsError):
        launcher.export_actor(original, exported)


def test_mixed_curriculum_requires_matches_and_bounded_stage_settings():
    profile = {**launcher.PROFILE, 'curriculum': 'wall-reset'}
    assert launcher.validate_profile(profile)['practice_fraction'] == .5
    for changes in ({'games': 1}, {'start_stage': 6}, {'start_stage': True},
                    {'practice_fraction': 1.}, {'practice_anchor': -1.},
                    {'curriculum_difficulty': float('nan')}, {'curriculum': 'unknown'}):
        with pytest.raises(ValueError):
            launcher.validate_profile({**profile, **changes})


def test_selection_source_preserves_actor_and_detects_tampering(tmp_path):
    from slater_team_eval import policy_digest
    actor_path = tmp_path / 'selected_actor.pt'
    launcher.export_actor(launcher.DEFAULT_RIVAL, actor_path)
    actor = launcher.torch.jit.load(str(actor_path), map_location='cpu')
    document = {'schema': 1, 'stage_complete': True, 'actor_path': str(actor_path),
                'exported_sha256': launcher.sha256(actor_path), 'actor_weights_sha256': policy_digest(actor),
                'status': 'EXPLORATORY_LEADER', 'model_id': 'fixture',
                'playing_model': str(launcher.DEFAULT_RIVAL), 'source_paths': []}
    path = tmp_path / 'selection.json'
    path.write_text(json.dumps(document))
    before = launcher.sha256(actor_path)
    source, metadata = launcher.source_from_selection(path)
    assert source == actor_path and metadata['confirmed_best'] is False
    assert launcher.sha256(actor_path) == before
    document['stage_complete'] = False
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='complete model-selection stage'):
        launcher.source_from_selection(path)
    document.update(stage_complete=True, actor_weights_sha256='0' * 64)
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='weights do not match'):
        launcher.source_from_selection(path)


def test_routine_aliases_formats_and_selfplay_bounds():
    wall = launcher.validate_profile({**launcher.PROFILE, 'curriculum': 'wall-reset'})
    assert wall['routine'] == 'wall-reset'
    air = launcher.validate_profile({**launcher.PROFILE, 'routine': 'air-control', 'start_stage': 5})
    assert air['curriculum'] == 'wall-reset' and air['start_stage'] == 2
    assert launcher.validate_profile({**launcher.PROFILE, 'formats': '1v1, 2v3,3v2'})['formats'] == '1v1,2v3,3v2'
    for changes in ({'formats': ''}, {'formats': '1v1,1v1'}, {'formats': '4v1'},
                    {'formats': '../1v1'}, {'selfplay_refresh': True}, {'selfplay_refresh': -1},
                    {'selfplay_refresh': 10001}, {'routine': 'unknown'},
                    {'routine': 'defense', 'games': 1},
                    {'routine': 'defense', 'curriculum': 'wall-reset'}):
        with pytest.raises(ValueError):
            launcher.validate_profile({**launcher.PROFILE, **changes})


def test_source_directory_resolves_only_a_complete_native_actor(tmp_path):
    checkpoint = tmp_path / 'checkpoint_000002'
    checkpoint.mkdir()
    for name in launcher.CHECKPOINT_FILES:
        (checkpoint / name).write_bytes(b'fixture')
    with pytest.raises(ValueError, match='Incomplete'):
        launcher.validate_source(checkpoint)
    (checkpoint / 'COMPLETE').write_text('complete')
    assert launcher.validate_source(checkpoint) == checkpoint / 'actor.pt'


def test_opponent_pool_keeps_fixed_exports_when_origin_json_changes(tmp_path):
    original = tmp_path / 'opponent.pt'
    launcher.export_actor(launcher.DEFAULT_RIVAL, original)
    pool_origin = tmp_path / 'pool.json'
    pool_origin.write_text(json.dumps({'actors': [{'id': 'aggressive', 'path': 'opponent.pt'}]}))
    run = tmp_path / 'run'
    pool = launcher.prepare_opponent_pool(run, pool_origin)
    manifest = launcher.read_json(run / 'opponent_pool.json')
    exported = Path(manifest['actors'][0]['path'])
    assert exported.parent == run / 'opponent_pool'
    assert manifest['actors'][0]['sha256'] == launcher.sha256(exported)
    source = {'path': str(original), 'sha256': launcher.sha256(original)}
    protocol = {key: source for key in ('source', 'teacher_source', 'rival_source')}
    protocol['opponent_pool'] = pool
    pool_origin.write_text(json.dumps({'actors': []}))
    launcher.verify_protected(protocol)  # Original JSON is provenance; copied manifest is authoritative.
    exported.write_bytes(exported.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Private opponent actor changed'):
        launcher.verify_protected(protocol)


@pytest.mark.parametrize('names', [['nexto'], ['Nexto'], ['source'], ['snapshot_1'],
                                  ['../escape'], ['а'], ['same', 'same'], ['same', 'SAME']])
def test_opponent_pool_rejects_reserved_duplicate_or_unsafe_ids(tmp_path, names):
    origin = tmp_path / 'pool.json'
    origin.write_text(json.dumps({'actors': [{'id': name, 'path': str(launcher.DEFAULT_RIVAL)} for name in names]}))
    with pytest.raises(ValueError, match='unique ASCII'):
        launcher.prepare_opponent_pool(tmp_path / 'run', origin)
    assert not list((tmp_path / 'run').rglob('*.pt'))


def test_native_command_always_uses_private_pool_and_new_profile_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.helper, 'meshes', lambda: tmp_path / 'meshes')
    empty = launcher.prepare_opponent_pool(tmp_path / 'run', '')
    assert launcher.read_json(empty['path']) == {'schema': 1, 'actors': []}
    cfg = launcher.validate_profile({**launcher.PROFILE, 'routine': 'defense',
                                     'formats': '1v1,2v2', 'selfplay_refresh': 20})
    command = launcher.native_command('train', tmp_path / 'run', cfg)
    flags = {str(command[index]): command[index + 1] for index in range(1, len(command), 2)}
    assert flags['--routine'] == 'defense' and flags['--formats'] == '1v1,2v2'
    assert flags['--selfplay-refresh'] == 20
    assert flags['--opponent-pool'] == tmp_path / 'run' / 'opponent_pool.json'


def test_training_pins_selection_snapshot_without_blocking_later_selector_stages(tmp_path, monkeypatch):
    from slater_team_eval import policy_digest
    selected_actor = tmp_path / 'selected.pt'
    launcher.export_actor(launcher.DEFAULT_RIVAL, selected_actor)
    actor = launcher.torch.jit.load(str(selected_actor), map_location='cpu')
    document = {'schema': 1, 'stage_complete': True, 'actor_path': str(selected_actor),
                'exported_sha256': launcher.sha256(selected_actor), 'actor_weights_sha256': policy_digest(actor),
                'status': 'EXPLORATORY', 'model_id': 'fixture', 'playing_model': str(launcher.DEFAULT_RIVAL),
                'source_paths': [{'path': str(selected_actor), 'sha256': launcher.sha256(selected_actor)}]}
    selection = tmp_path / 'selection.json'
    selection.write_text(json.dumps(document))
    run = tmp_path / 'training'
    monkeypatch.setattr(launcher, 'run_path', lambda name: run)
    monkeypatch.setattr(launcher, 'binary_identity', lambda build: {})
    monkeypatch.setattr(launcher, 'code_identity', lambda: {})
    def complete_process(command, log, **kwargs):
        checkpoint = run / 'checkpoints' / 'checkpoint_000001'
        checkpoint.mkdir(parents=True)
        for name in launcher.CHECKPOINT_FILES:
            (checkpoint / name).write_bytes(b'fixture')
        (checkpoint / 'COMPLETE').write_text('ok')
        return {'updates': 1, 'decisions': 64}
    monkeypatch.setattr(launcher, 'checked_process', complete_process)
    launcher.train('fixture', updates=1, selection=selection, profile={**launcher.PROFILE, 'device': 'cpu'})
    saved = launcher.read_json(run / 'protocol.json')
    assert saved['selection']['path'] == str(run / 'selection_at_start.json')
    assert saved['selection']['origin_path'] == str(selection)
    document['status'] = 'LATER_SELECTOR_STAGE'
    selection.write_text(json.dumps(document))
    launcher.check_run('fixture')
    snapshot = run / 'selection_at_start.json'
    snapshot.write_bytes(snapshot.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Selection document changed'):
        launcher.check_run('fixture')


@pytest.mark.parametrize('command', ['parity', 'eval', 'benchmark', 'export', 'build', 'status'])
def test_selection_is_rejected_before_unrelated_cli_actions(monkeypatch, command):
    monkeypatch.setattr(sys, 'argv', ['slater_native_attention.py', command, '--selection', 'selection.json'])
    with pytest.raises(SystemExit) as error:
        launcher.main()
    assert error.value.code == 2
