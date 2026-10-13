import json
from pathlib import Path

import pytest

import slater_native_attention as launcher


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
