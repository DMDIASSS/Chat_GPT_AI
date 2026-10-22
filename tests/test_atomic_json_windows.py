"""Windows sharing violations must not corrupt or discard durable JSON."""
import json

import pytest

import slater_v041_core as core


def windows_lock(code):
    error = PermissionError('File is temporarily held by a Windows reader')
    error.winerror = code
    return error


@pytest.mark.parametrize('code', [5, 32, 33])
def test_temporary_reader_lock_preserves_old_json_until_success(tmp_path, monkeypatch, code):
    path = tmp_path / 'progress.json'
    core.atomic_json(path, {'updates': 10})
    replace = core.os.replace
    calls = []

    def sometimes_locked(source, destination):
        calls.append(destination)
        assert json.loads(path.read_text()) == {'updates': 10}
        if len(calls) < 3:
            raise windows_lock(code)
        replace(source, destination)

    monkeypatch.setattr(core.os, 'replace', sometimes_locked)
    monkeypatch.setattr(core.time, 'sleep', lambda delay: None)
    core.atomic_json(path, {'updates': 11})
    assert len(calls) == 3
    assert json.loads(path.read_text()) == {'updates': 11}
    assert not list(tmp_path.glob('*.writing.*'))


def test_persistent_lock_is_bounded_and_keeps_last_complete_file(tmp_path, monkeypatch):
    path = tmp_path / 'progress.json'
    core.atomic_json(path, {'updates': 10})
    delays = []
    monkeypatch.setattr(core.os, 'replace', lambda *args: (_ for _ in ()).throw(windows_lock(5)))
    monkeypatch.setattr(core.time, 'sleep', delays.append)
    with pytest.raises(PermissionError):
        core.atomic_json(path, {'updates': 11})
    assert len(delays) == 8 and sum(delays) < 2
    assert json.loads(path.read_text()) == {'updates': 10}
    assert not list(tmp_path.glob('*.writing.*'))


def test_other_permission_failures_are_not_hidden_or_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(core.os, 'replace', lambda *args: (_ for _ in ()).throw(PermissionError('read only')))
    monkeypatch.setattr(core.time, 'sleep', lambda delay: pytest.fail('Not a Windows sharing/access violation'))
    with pytest.raises(PermissionError, match='read only'):
        core.atomic_json(tmp_path / 'config.json', {'updates': 1})
    assert not list(tmp_path.glob('*.writing.*'))


def test_serialization_error_cleans_up_without_replacing_previous_file(tmp_path):
    path = tmp_path / 'config.json'
    core.atomic_json(path, {'valid': True})
    with pytest.raises(TypeError):
        core.atomic_json(path, {'bad': object()})
    assert json.loads(path.read_text()) == {'valid': True}
    assert not list(tmp_path.glob('*.writing.*'))
