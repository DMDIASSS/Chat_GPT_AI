"""Supervisor contracts: immutable runs, local credentials and durable events."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import slater_freestyle as freestyle
from GigaLearn_Project.Native_Backend import native_setup


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(freestyle, 'BASE', tmp_path / 'freestyle')
    identity = {'binary_sha256': 'native-build-one', 'backend_sha': {'trainer.cpp': 'source-one'},
                'gigalearn_commit': 'pinned-upstream'}
    monkeypatch.setattr(freestyle, 'binary_identity', lambda folder=None: deepcopy(identity))
    binary = tmp_path / 'bin' / 'SlaterFreestyleNative'
    binary.parent.mkdir()
    binary.write_text('test process stub', encoding='utf-8')
    monkeypatch.setattr(freestyle, 'binary_path', lambda folder=None: binary)
    monkeypatch.setattr(native_setup, 'meshes', lambda: tmp_path / 'collision_meshes')
    captured = {'identity': identity, 'binary': binary, 'children': [], 'monitors': []}

    class Monitor:
        def __init__(self, *args, **kwargs):
            self.state = {}
            self.events = []
            self.closed = False
            captured['monitors'].append(self)

        def submit(self, event):
            self.events.append(deepcopy(event))

        def close(self):
            self.closed = True

    monkeypatch.setattr(freestyle, 'WandbMonitor', Monitor)
    monkeypatch.setattr(native_setup, 'runtime_environment', lambda *args: {
        'WANDB_API_KEY': 'local-api-key-do-not-persist',
        'WANDB_ACCESS_TOKEN': 'local-access-token',
        'WANDB_IDENTITY_TOKEN_FILE': 'local-identity-secret-path',
        'CUDA_PATH': '/local/cuda', 'PATH': '/local/bin',
    })

    def spawn(args, **kwargs):
        launch = {'args': list(args), 'kwargs': kwargs,
                  'settings': freestyle.read_json(args[args.index('--config') + 1])}
        captured['children'].append(launch)
        kwargs['stdout'].write(b'FREESTYLE_COMPLETE {"status":"COMPLETE","total_updates":3,"total_timesteps":3072}\n')
        kwargs['stdout'].flush()
        return SimpleNamespace(pid=5678, poll=lambda: 0)

    monkeypatch.setattr(freestyle.subprocess, 'Popen', spawn)
    return captured


@pytest.mark.parametrize('credential', ['api_key', 'WANDB_API_KEY', 'token', 'password', 'Authorization'])
def test_nested_credentials_are_refused_before_run_files_exist(isolated_runtime, credential):
    settings = freestyle.defaults()
    settings['native']['rewards'] = {'nested': [{credential: 'secret-from-settings'}]}
    with pytest.raises(ValueError, match='credential'):
        freestyle.initialize('unsafe_settings', settings)
    assert not freestyle.run_path('unsafe_settings').exists()


def test_native_child_does_not_receive_wandb_credentials(isolated_runtime):
    freestyle.train('redacted_child', freestyle.defaults(), updates=1)
    environment = isolated_runtime['children'][0]['kwargs']['env']
    assert not any(key in environment for key in freestyle.REDACT_ENV)
    assert environment['CUDA_PATH'] == '/local/cuda'
    assert environment['PATH'] == '/local/bin'
    assert environment['PYTHONUNBUFFERED'] == '1'
    for path in freestyle.run_path('redacted_child').rglob('*'):
        if path.is_file():
            assert b'local-api-key-do-not-persist' not in path.read_bytes()
            assert b'local-access-token' not in path.read_bytes()
    assert isolated_runtime['monitors'][0].closed


def test_resume_uses_saved_immutable_settings_not_editor_changes(isolated_runtime):
    initial = freestyle.defaults()
    folder, protocol = freestyle.initialize('immutable', initial)
    changed = freestyle.defaults()
    changed['native']['width'] = 1024
    changed['native']['tick_skip'] = 8
    resumed_folder, resumed_protocol = freestyle.initialize('immutable', changed, resume=True)
    assert resumed_folder == folder
    assert resumed_protocol == protocol
    assert resumed_protocol['settings']['native']['width'] == initial['native']['width']
    assert resumed_protocol['settings']['native']['tick_skip'] == initial['native']['tick_skip']


def test_resume_refuses_config_file_tampering(isolated_runtime):
    folder, _ = freestyle.initialize('edited', freestyle.defaults())
    native = freestyle.read_json(folder / 'config.json')
    native['actor_lr'] *= 2
    freestyle.atomic_json(folder / 'config.json', native)
    with pytest.raises(ValueError, match='configuration was edited'):
        freestyle.initialize('edited', freestyle.defaults(), resume=True)


def test_resume_refuses_different_native_build(isolated_runtime):
    freestyle.initialize('old_build', freestyle.defaults())
    isolated_runtime['identity']['binary_sha256'] = 'native-build-two'
    with pytest.raises(ValueError, match='another Freestyle build'):
        freestyle.initialize('old_build', freestyle.defaults(), resume=True)


def test_start_never_overwrites_existing_run(isolated_runtime):
    folder, _ = freestyle.initialize('existing', freestyle.defaults())
    before = (folder / 'protocol.json').read_bytes()
    with pytest.raises(FileExistsError, match='Resume'):
        freestyle.initialize('existing', freestyle.defaults())
    assert (folder / 'protocol.json').read_bytes() == before


@pytest.mark.parametrize('name', ['../old_champion', '/absolute', 'with space', 'nested/run', ''])
def test_run_path_is_confined_to_freestyle_area(name):
    with pytest.raises(ValueError, match='run name'):
        freestyle.run_path(name)


def test_event_reader_retries_partial_write_without_duplicate_events(tmp_path):
    stream = tmp_path / 'events.jsonl'
    first = b'{"update":1,"stage":"contact_pop"}\n'
    stream.write_bytes(first + b'{"update":2,"stage":"air_')
    reader = freestyle.EventReader(tmp_path)
    assert reader.read() == [{'update': 1, 'stage': 'contact_pop'}]
    assert reader.offset == len(first)
    assert reader.read() == []
    with stream.open('ab') as handle:
        handle.write(b'carry"}\n')
    assert reader.read() == [{'update': 2, 'stage': 'air_carry'}]
    assert reader.read() == []
    assert reader.offset == stream.stat().st_size


def test_event_reader_counts_utf8_bytes_when_resuming(tmp_path):
    stream = tmp_path / 'events.jsonl'
    first = json.dumps({'update': 1, 'note': 'тест'}, ensure_ascii=False).encode() + b'\n'
    second = b'{"update":2}\n'
    stream.write_bytes(first + second)
    reader = freestyle.EventReader(tmp_path, offset=len(first))
    assert reader.read() == [{'update': 2}]


def test_event_reader_requires_json_objects(tmp_path):
    (tmp_path / 'events.jsonl').write_text('[1,2]\n', encoding='utf-8')
    with pytest.raises(ValueError, match='JSON object'):
        freestyle.EventReader(tmp_path).read()


def test_hidden_login_exception_never_prints_key(monkeypatch, capsys):
    key = 'locally-entered-key-that-must-not-appear'
    monkeypatch.delenv('WANDB_API_KEY', raising=False)
    monkeypatch.delenv('WANDB_IDENTITY_TOKEN_FILE', raising=False)
    monkeypatch.setattr(freestyle, 'credential_prompt', lambda: key)
    import netrc
    monkeypatch.setattr(netrc, 'netrc', lambda: SimpleNamespace(authenticators=lambda host: None))

    def login(**kwargs):
        assert kwargs['key'] == key
        raise RuntimeError('SDK request included Authorization: ' + key)

    assert freestyle.configure_login(SimpleNamespace(login=login), 'online') is False
    captured = capsys.readouterr()
    assert key not in captured.out + captured.err
    assert 'login failed' in captured.out


def test_configured_key_is_used_without_prompt(monkeypatch):
    monkeypatch.setenv('WANDB_API_KEY', 'existing-local-credential')
    monkeypatch.setattr(freestyle, 'credential_prompt', lambda: pytest.fail('Existing W&B credential should not be requested again'))
    calls = []
    assert freestyle.configure_login(SimpleNamespace(login=lambda **kw: calls.append(kw) or True), 'online')
    assert calls == [{'verify': True, 'timeout': 20}]


@pytest.mark.parametrize('mode', ['offline', 'disabled'])
def test_offline_modes_do_not_request_credentials(monkeypatch, mode):
    monkeypatch.setattr(freestyle, 'credential_prompt', lambda: pytest.fail('Offline mode must not ask for a key'))
    assert freestyle.configure_login(SimpleNamespace(login=lambda **kwargs: pytest.fail('No online login required')), mode)


def test_additional_update_budget_is_not_written_into_immutable_config(isolated_runtime):
    folder, _ = freestyle.initialize('additional_budget', freestyle.defaults())
    freestyle.atomic_json(folder / 'progress.json', {'status': 'PAUSED', 'updates': 7, 'timesteps': 7168})
    before = (folder / 'config.json').read_bytes()
    freestyle.train('additional_budget', freestyle.defaults(), resume=True, updates=3)
    launch = isolated_runtime['children'][0]
    assert launch['settings']['max_updates'] == 10
    assert '--resume' in launch['args']
    assert (folder / 'config.json').read_bytes() == before


def test_zero_update_budget_means_unlimited(isolated_runtime):
    freestyle.train('unlimited', freestyle.defaults(), updates=0)
    assert isolated_runtime['children'][0]['settings']['max_updates'] == 0


def test_completion_totals_are_authoritative_if_last_event_was_not_read(isolated_runtime):
    result = freestyle.train('completion_counts', freestyle.defaults(), updates=3)
    assert result['status'] == 'COMPLETE'
    assert result['updates'] == 3
    assert result['timesteps'] == 3072


def test_resume_budget_starts_from_complete_checkpoint_not_stale_ui_progress(isolated_runtime):
    folder, _ = freestyle.initialize('stale_ui', freestyle.defaults())
    freestyle.atomic_json(folder / 'progress.json', {'status': 'ERROR', 'updates': 4, 'timesteps': 4096})
    checkpoint = folder / 'checkpoints' / '7168'
    checkpoint.mkdir(parents=True)
    complete = {'schema': 'slater-freestyle-state-v1', 'update': 7, 'timesteps': 7168,
                'source_sha': 'source-one', 'state_file': 'FREESTYLE_STATE.json'}
    freestyle.atomic_json(checkpoint / 'FREESTYLE_COMPLETE.json', complete)
    freestyle.atomic_json(folder / 'latest.json', {**complete, 'checkpoint': str(checkpoint)})
    freestyle.train('stale_ui', freestyle.defaults(), resume=True, updates=3)
    assert isolated_runtime['children'][0]['settings']['max_updates'] == 10


def test_invalid_budget_has_no_leaked_monitor_or_child(isolated_runtime):
    with pytest.raises(ValueError, match='updates'):
        freestyle.train('negative_budget', freestyle.defaults(), updates=-1)
    assert isolated_runtime['children'] == []
    assert all(monitor.closed for monitor in isolated_runtime['monitors'])


def test_supervisor_error_keeps_run_lock_until_native_has_stopped(isolated_runtime, monkeypatch):
    state = {'locked': False, 'polls_after_pause': 0, 'process_stopped': False}
    pause_file = freestyle.run_path('metrics_error') / 'PAUSE'

    @contextmanager
    def lock(path):
        if str(path).endswith('.telemetry.lock'):
            yield
            return
        assert not state['locked']
        state['locked'] = True
        try:
            yield
        finally:
            assert state['process_stopped'], 'Releasing the lock while a native writer is alive permits a corrupting resume'
            state['locked'] = False

    class Reader:
        def __init__(self, folder, **kwargs):
            pass

        def read(self):
            raise ValueError('Malformed native metric line')

    def poll():
        assert state['locked']
        if pause_file.exists():
            state['polls_after_pause'] += 1
            if state['polls_after_pause'] >= 2:
                state['process_stopped'] = True
                return 0
        return None

    monkeypatch.setattr(freestyle, 'process_lock', lock)
    monkeypatch.setattr(freestyle, 'EventReader', Reader)
    monkeypatch.setattr(freestyle.subprocess, 'Popen', lambda *args, **kwargs:
                        SimpleNamespace(pid=5678, poll=poll, wait=lambda timeout=None: poll()))
    monkeypatch.setattr(freestyle.time, 'sleep', lambda seconds: None)
    with pytest.raises(ValueError, match='Malformed native'):
        freestyle.train('metrics_error', freestyle.defaults())
    assert pause_file.exists()
    assert state['process_stopped']
    assert not state['locked']
    assert isolated_runtime['monitors'][0].closed


@pytest.mark.parametrize('change', [
    {'tick_skip': 3, 'action_delay': 1}, {'epochs': 9},
    {'steps_per_update': 256, 'minibatch': 128}, {'minibatch': 64},
    {'eval_episodes': 257}, {'mastery_passes': 21},
])
def test_python_configuration_refuses_values_rejected_by_native(change):
    settings = freestyle.defaults()
    settings['native'].update(change)
    with pytest.raises(ValueError):
        freestyle.validate_settings(settings)


def test_settings_cannot_select_unknown_curriculum_stage():
    settings = freestyle.defaults()
    settings['native']['stage'] = 'not_a_stage'
    with pytest.raises(ValueError, match='stage'):
        freestyle.validate_settings(settings)


@pytest.fixture
def fake_wandb(tmp_path, monkeypatch):
    calls = []
    handles = []

    class Handle:
        url = 'https://wandb.ai/test/slater-freestyle/runs/persisted-run-id'
        step = 0

        def __init__(self):
            self.logged = []
            self.saved = []
            self.finished = False

        def define_metric(self, *args, **kwargs):
            pass

        def save(self, *args, **kwargs):
            self.saved.append((args, kwargs))

        def log(self, values, step):
            self.logged.append((step, values))
            self.step = step + 1

        def finish(self):
            self.finished = True

    def initialize(**kwargs):
        calls.append(kwargs)
        handle = Handle()
        handles.append(handle)
        return handle

    # W&B 0.30 has no public wandb.util.generate_id; initialization must not
    # rely on it. The supervisor's generated identity must survive resume.
    sdk = SimpleNamespace(init=initialize, Settings=lambda **kwargs: kwargs)
    monkeypatch.setitem(sys.modules, 'wandb', sdk)
    monkeypatch.setattr(freestyle, 'configure_login', lambda *args, **kwargs: True)
    return SimpleNamespace(calls=calls, handles=handles, folder=tmp_path)


def test_offline_to_online_replays_metrics_that_never_reached_server(fake_wandb):
    settings = freestyle.defaults()['wandb']
    settings['mode'] = 'offline'
    offline = freestyle.WandbMonitor(fake_wandb.folder, settings, {'initialization': 'random_weights'})
    offline.submit({'update': 1, 'metrics': {'Rewards/air_touch': .4}})
    offline.submit({'update': 2, 'metrics': {'Rewards/air_touch': .8}})
    offline.queue.join()
    offline.close()
    assert [step for step, _ in fake_wandb.handles[0].logged] == [1, 2]

    settings['mode'] = 'online'
    online = freestyle.WandbMonitor(fake_wandb.folder, settings, {'initialization': 'random_weights'})
    try:
        online.submit({'update': 1, 'metrics': {'Rewards/air_touch': .4}})
        online.submit({'update': 2, 'metrics': {'Rewards/air_touch': .8}})
        online.queue.join()
        assert [step for step, _ in fake_wandb.handles[1].logged] == [1, 2]
        assert fake_wandb.calls[0]['id'] == fake_wandb.calls[1]['id']
        assert len(fake_wandb.calls[0]['id']) == 8
        assert fake_wandb.calls[1]['resume'] == 'allow'
    finally:
        online.close()


def test_online_resume_skips_events_already_uploaded(fake_wandb):
    settings = freestyle.defaults()['wandb']
    first = freestyle.WandbMonitor(fake_wandb.folder, settings, {'initialization': 'random_weights'})
    first.submit({'update': 1, 'metrics': {'touches': 5}})
    first.queue.join()
    first.close()
    resumed = freestyle.WandbMonitor(fake_wandb.folder, settings, {'initialization': 'random_weights'})
    try:
        resumed.submit({'update': 1, 'metrics': {'touches': 5}})
        resumed.submit({'update': 2, 'metrics': {'touches': 7}})
        resumed.queue.join()
        assert [step for step, _ in fake_wandb.handles[1].logged] == [2]
        assert fake_wandb.calls[0]['id'] == fake_wandb.calls[1]['id']
    finally:
        resumed.close()


def test_windows_progress_lock_cannot_stop_native_training(isolated_runtime, monkeypatch, capsys):
    write = freestyle.atomic_json

    def blocked_status(path, data):
        if Path(path).name == 'progress.json' and data.get('updates') == 1:
            error = PermissionError('progress.json is held by a Windows reader')
            error.winerror = 5
            raise error
        write(path, data)

    class Reader:
        def __init__(self, folder):
            self.done = False

        def read(self):
            if self.done:
                return []
            self.done = True
            return [{'update': 1, 'timesteps': 1024}, {'update': 2, 'timesteps': 2048}]

    monkeypatch.setattr(freestyle, 'atomic_json', blocked_status)
    monkeypatch.setattr(freestyle, 'EventReader', Reader)
    result = freestyle.train('locked_status', freestyle.defaults(), updates=3)
    assert result['status'] == 'COMPLETE' and result['updates'] == 3
    assert freestyle.read_json(freestyle.run_path('locked_status') / 'progress.json')['updates'] == 3
    assert not (freestyle.run_path('locked_status') / 'PAUSE').exists()
    assert [event['update'] for event in isolated_runtime['monitors'][0].events] == [1, 2]
    assert 'FREESTYLE_STATUS_WARNING' in capsys.readouterr().out


def test_status_writer_does_not_hide_unrelated_permissions(tmp_path, monkeypatch):
    def fail(*args):
        raise PermissionError('unrelated permission failure')

    monkeypatch.setattr(freestyle, 'atomic_json', fail)
    with pytest.raises(PermissionError, match='unrelated'):
        freestyle.write_progress(tmp_path, {'updates': 1})


def test_wandb_registers_copies_and_never_live_status_files(fake_wandb):
    folder = fake_wandb.folder
    (folder / 'config.json').write_text('{"width":768}')
    monitor = freestyle.WandbMonitor(folder, freestyle.defaults()['wandb'], {})
    (folder / 'progress.json').write_text('{"updates":2612}')
    monitor.close()
    handle = fake_wandb.handles[0]
    snapshots = [Path(args[0]) for args, kwargs in handle.saved]
    assert {path.name for path in snapshots} == {'config.json', 'progress.json'}
    assert all(path.parent.parent == folder / 'wandb_uploads' for path in snapshots)
    (folder / 'progress.json').write_text('{"updates":2613}')
    copied_progress = next(path for path in snapshots if path.name == 'progress.json')
    assert json.loads(copied_progress.read_text()) == {'updates': 2612}
    assert handle.finished


def test_snapshot_upload_failure_still_finishes_wandb(fake_wandb, monkeypatch):
    monitor = freestyle.WandbMonitor(fake_wandb.folder, freestyle.defaults()['wandb'], {})
    (fake_wandb.folder / 'progress.json').write_text('{"updates":1}')

    def upload_failure(*args, **kwargs):
        raise PermissionError('file upload temporarily unavailable')

    monkeypatch.setattr(fake_wandb.handles[0], 'save', upload_failure)
    monitor.close()
    assert fake_wandb.handles[0].finished
