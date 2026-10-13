"""Headless checks for Studio configuration, process lifecycle and real exports."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

import pytest

import slater_training_studio as studio


def test_visual_studio_bootstrap_passes_cmd_quotes_unchanged(monkeypatch, tmp_path):
    from types import SimpleNamespace
    programs = tmp_path / 'Program Files (x86)'
    vswhere = programs / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vswhere.parent.mkdir(parents=True); vswhere.touch()
    installation = programs / 'Microsoft Visual Studio/2022/BuildTools'
    vcvars = installation / 'VC/Auxiliary/Build/vcvars64.bat'
    vcvars.parent.mkdir(parents=True); vcvars.touch()
    monkeypatch.setattr(studio, 'os', SimpleNamespace(name='nt', environ={'ProgramFiles(x86)': str(programs)}))
    environment = {'PATH': 'original'}
    calls = []
    def check_output(command, **kwargs):
        calls.append(command)
        if isinstance(command, list):
            assert command[0] == str(vswhere)
            return str(installation) + '\n'
        assert command == f'cmd.exe /d /s /c "call "{vcvars}" >nul && set"'
        assert '\\"' not in command
        assert kwargs['env'] == environment
        return 'VSCMD_ARG_TGT_ARCH=x64\nPATH=compiler;original\nVALUE=with=equals\n'
    monkeypatch.setattr(studio.subprocess, 'check_output', check_output)
    result = studio.initialize_visual_studio(environment)
    assert len(calls) == 2 and isinstance(calls[1], str)
    assert result == {'VSCMD_ARG_TGT_ARCH': 'x64', 'PATH': 'compiler;original', 'VALUE': 'with=equals'}
    assert environment == {'PATH': 'original'}


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows cmd.exe')
def test_actual_windows_cmd_bootstrap_spaces_parentheses_and_failure(tmp_path):
    vcvars = tmp_path / 'Visual Studio (x86)' / 'vcvars64.bat'
    vcvars.parent.mkdir()
    vcvars.write_bytes(b'@echo off\r\nset "SLATER_BOOTSTRAP_TEST=x64-ready"\r\nexit /b 0\r\n')
    output = subprocess.check_output(studio.visual_studio_command(vcvars), text=True, env=os.environ.copy())
    assert 'SLATER_BOOTSTRAP_TEST=x64-ready' in output.splitlines()
    vcvars.write_bytes(b'@echo off\r\nexit /b 9\r\n')
    with pytest.raises(subprocess.CalledProcessError) as error:
        subprocess.check_output(studio.visual_studio_command(vcvars), text=True, env=os.environ.copy())
    assert error.value.returncode == 9


def model_settings(tmp_path):
    source = tmp_path / 'models with spaces' / 'best $model.pt'
    source.parent.mkdir(); source.write_bytes(b'fixture')
    return {**studio.default_settings(), 'source': str(source)}


def test_paths_are_single_arguments_and_resume_keeps_saved_protocol(tmp_path):
    settings = model_settings(tmp_path)
    command = studio.command_for('native', 'train', settings, root=tmp_path, interpreter='python')
    assert command[command.index('--source') + 1] == settings['source']
    assert command[command.index('--routine') + 1] == 'match'
    assert command[command.index('--formats') + 1] == '1v1,2v2,3v3'
    settings['native_profile']['actor_lr'] = 4e-5
    resumed = studio.command_for('native', 'resume', settings, root=tmp_path, interpreter='python')
    assert '--actor-lr' not in resumed and '--source' not in resumed
    assert resumed[-2:] == ['--updates', '100']


def test_selection_takes_precedence_without_requiring_a_missing_source(tmp_path):
    settings = studio.default_settings()
    settings['selection'] = str(tmp_path / 'selection.json')
    settings['source'] = str(tmp_path / 'missing.pt')
    command = studio.command_for('native', 'train', settings, root=tmp_path, interpreter='python')
    assert '--selection' in command and '--source' not in command
    campaign = studio.command_for('campaign', 'run', settings, config_file=tmp_path / 'campaign.json', root=tmp_path)
    assert '--selection' in campaign and '--source' not in campaign


def test_all_nine_format_preset_keeps_native_and_campaign_guards_consistent():
    settings = studio.default_settings()
    settings['campaign']['native_profile'] = {'formats': '1v1', 'actor_lr': 1e-6}
    expanded = studio.format_preset(settings, True)
    modes = expanded['campaign']['formats']
    assert len(modes) == 9 and '1v3' in modes and '3v1' in modes
    assert expanded['native_profile']['formats'] == ','.join(modes)
    assert expanded['campaign']['native_profile']['formats'] == ','.join(modes)
    assert expanded['campaign']['native_profile']['actor_lr'] == 1e-6
    assert sum(expanded['campaign']['mode_weights'].values()) == pytest.approx(1)
    restored = studio.format_preset(expanded, False)
    assert restored['campaign']['formats'] == ['1v1', '2v2', '3v3']


def test_replay_prepare_is_bounded_and_confined_to_private_data(tmp_path):
    settings = studio.default_settings()
    settings['replays']['inputs'] = str(tmp_path / 'raw replays with spaces')
    command = studio.command_for('replay', 'prepare', settings, root=tmp_path, interpreter='python')
    assert command[command.index('--inputs') + 1] == settings['replays']['inputs']
    assert command[command.index('--max-replays') + 1] == '100'
    settings['replays']['output'] = str(tmp_path / 'original models')
    with pytest.raises(ValueError, match='data/isolated'):
        studio.command_for('replay', 'prepare', settings, root=tmp_path)
    settings['replays']['audit_checkpoint'] = str(tmp_path / 'legacy checkpoint folder')
    audit = studio.command_for('replay', 'audit', settings, root=tmp_path)
    assert audit[-2:] == ['--checkpoint', settings['replays']['audit_checkpoint']]


def test_selector_resume_extends_budget_without_changing_cached_protocol(tmp_path):
    settings = studio.default_settings()
    settings.update(max_games=2048, until='confirm')
    fresh = studio.command_for('selector', 'run', settings, config_file=tmp_path / 'options.json')
    resumed = studio.command_for('selector', 'resume', settings, config_file=tmp_path / 'changed.json')
    assert '--config' in fresh and '--config' not in resumed
    assert resumed[-4:] == ['--max-games', '2048', '--until', 'confirm']
    folder = studio.result_directory('selector', settings['selector_run'], tmp_path)
    folder.mkdir(parents=True); (folder / 'config.json').write_text('{}')
    inventoried = studio.command_for('selector', 'run', settings, config_file=tmp_path / 'changed.json', root=tmp_path)
    assert inventoried[2] == 'resume' and '--config' not in inventoried


def test_common_profiles_agree_with_native_and_campaign_backends():
    import slater_native_attention as native
    import slater_champion_campaign as campaign
    settings = studio.default_settings()
    profile = native.validate_profile(settings['native_profile'])
    assert profile['formats'] == '1v1,2v2,3v3'
    assert profile['selfplay_refresh'] == 10
    config = campaign.validate_config({'native_profile': settings['native_profile']})
    assert config['branch_updates'] >= config['chunk_updates']
    assert config['native_profile']['teacher_weight'] == .1


def test_explicit_campaign_parameters_survive_common_form_defaults():
    settings = studio.default_settings()
    settings['campaign'] = {'native_profile': {'actor_lr': 1e-6}, 'branch_updates': 200}
    config = studio.job_config('campaign', settings)
    assert config['native_profile']['actor_lr'] == 1e-6
    assert config['native_profile']['games'] == 8
    assert config['branch_updates'] == 200
    assert settings['campaign']['native_profile'] == {'actor_lr': 1e-6}


def test_campaign_champion_is_loaded_only_when_its_actor_hash_matches(tmp_path):
    settings = studio.default_settings()
    run = studio.result_directory('campaign', settings['campaign_run'], tmp_path)
    run.mkdir(parents=True)
    actor = run / 'champion.pt'; actor.write_bytes(b'protected actor')
    payload = {'actor_path': str(actor), 'exported_sha256': studio.hashlib.sha256(actor.read_bytes()).hexdigest()}
    studio.atomic_json(run / 'selected.json', payload)
    assert studio.campaign_champion(settings, tmp_path) == actor
    actor.write_bytes(b'changed actor')
    with pytest.raises(ValueError, match='changed'):
        studio.campaign_champion(settings, tmp_path)


@pytest.mark.parametrize('changes', [
    {'native_run': '../overwrite'}, {'updates': 0}, {'max_games': 100001},
    {'eval_seconds': float('inf')}, {'campaign': {'ballchasing_api_key': 'secret'}},
    {'selector': {'nested': [{'token': 'secret'}]}},
    {'native_profile': {'actor_lr': -.1}}, {'native_profile': {'unknown_flag': 1}},
])
def test_rejects_bad_names_budgets_and_credentials(changes):
    with pytest.raises(ValueError):
        studio.validate_settings(changes)


def test_native_folder_discovery_excludes_partial_and_lists_accepted(tmp_path):
    mechanics = tmp_path / 'data/isolated/mechanics_curriculum/selected7_mechanics01'
    mechanics.mkdir(parents=True)
    for name in ('update_000278.pt', 'accepted_000020.pt'):
        (mechanics / name).write_bytes(b'model')
    complete = tmp_path / 'data/isolated/native_attention/runs/run01/checkpoints/checkpoint_000197'
    partial = complete.with_name('checkpoint_000198')
    for folder in (complete, partial):
        folder.mkdir(parents=True); (folder / 'actor.pt').write_bytes(b'actor')
    (complete / 'COMPLETE').touch()
    rows = studio.discover_checkpoints(tmp_path)
    assert len(rows) == 3
    assert {'update_000278.pt', 'accepted_000020.pt', 'checkpoint_000197'} == {row['name'] for row in rows}
    assert studio.source_file(complete) == complete / 'actor.pt'
    with pytest.raises(ValueError, match='completed'):
        studio.source_file(partial)


def test_evaluation_explicit_checkpoint_and_kickoff_export(tmp_path):
    settings = model_settings(tmp_path)
    settings['checkpoint'] = str(tmp_path / 'checkpoint_000097')
    evaluate = studio.command_for('native', 'eval', settings)
    assert evaluate[-2:] == ['--checkpoint', settings['checkpoint']]
    export = studio.command_for('export', 'export', settings)
    assert export[-2:] == ['--export-kickoff', 'both']


def test_structured_progress_preserves_metrics_without_inventing_a_promotion():
    result = studio.progress_from_line('SLATER_ATTENTION_UPDATE {"update": 197, "ppo": {"teacher_kl": 0.02}}')
    assert result['update'] == 197
    assert result['ppo']['teacher_kl'] == .02
    assert 'confirmed_best' not in result
    assert studio.progress_from_line('random chatter {"update":1}') is None
    assert studio.progress_from_line('SLATER_ATTENTION_UPDATE broken-json') is None


def test_durable_worker_reconnects_and_guards_concurrent_jobs(tmp_path):
    manager = studio.ProcessManager(base=tmp_path / 'studio')
    argv = [sys.executable, '-u', '-c', 'import time; print("started", flush=True); time.sleep(1.5); print("finished")']
    job = manager.start(argv, 'native', 'train', 'run01')
    assert manager.active
    with pytest.raises(RuntimeError, match='already running'):
        manager.start(argv, 'native', 'train', 'run02')
    recovered = studio.ProcessManager(base=tmp_path / 'studio')
    assert recovered.active and recovered.job['pid'] == job['pid']
    manager.process.wait(timeout=10)
    assert recovered.process.poll() == 0
    assert not recovered.active
    log = Path(job['log']).read_text()
    assert 'started' in log and 'finished' in log and 'STUDIO_JOB_COMPLETE' in log
    assert json.loads(Path(job['result']).read_text())['returncode'] == 0


def test_worker_failure_is_reported_durably(tmp_path):
    manager = studio.ProcessManager(base=tmp_path / 'studio')
    job = manager.start([sys.executable, '-c', 'raise SystemExit(7)'], 'native', 'smoke', 'run01')
    assert manager.process.wait(timeout=10) == 7
    assert json.loads(Path(job['result']).read_text())['returncode'] == 7


def test_export_reuses_checked_rlbot_exporter_and_keeps_source(monkeypatch, tmp_path):
    source = studio.ROOT / 'vendor/nexto/nexto-model.pt'
    if not source.is_file():
        pytest.skip('Real attention actor fixture is unavailable')
    import export_rlbot_v4 as exporter
    import torch
    monkeypatch.setattr(studio, 'BASE', tmp_path / 'studio')
    monkeypatch.setattr(exporter, 'OUTPUT', tmp_path / 'rlbot_exports')
    before = source.read_bytes()
    studio.export_worker(str(source), 'FixtureChampion', 'both')
    for mode, scripted in (('Learned', False), ('Scripted', True)):
        folder = tmp_path / 'rlbot_exports' / ('FixtureChampion_' + mode)
        info = json.loads((folder / 'EXPORT_INFO.json').read_text())
        assert info['hardcoded_kickoffs'] is scripted
        assert (folder / 'bot.cfg').is_file()
        actor = torch.jit.load(str(folder / 'nexto-model.pt'), map_location='cpu')
        original = torch.jit.load(str(source), map_location='cpu')
        assert all(torch.equal(value, actor.state_dict()[key]) for key, value in original.state_dict().items())
    assert source.read_bytes() == before
    with pytest.raises(FileExistsError):
        studio.export_worker(str(source), 'FixtureChampion', 'both')
