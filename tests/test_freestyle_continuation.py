"""Revised rewards preserve a compatible parent actor without rewriting its run."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import slater_freestyle as freestyle
from GigaLearn_Project.Native_Backend import native_setup


@pytest.fixture
def parent(tmp_path, monkeypatch):
    monkeypatch.setattr(freestyle, 'BASE', tmp_path)
    identity = {'binary_sha256': 'old-build', 'backend_sha': {
        filename: freestyle.sha256(freestyle.HERE / filename)
        for filename in ('FreestyleObs.h', 'FreestyleActions.h')}}
    monkeypatch.setattr(freestyle, 'binary_identity', lambda folder=None: deepcopy(identity))
    source, _ = freestyle.initialize('overnight', freestyle.defaults())
    complete = {'schema': 1, 'source_sha': 'old-native-source', 'update': 2612, 'timesteps': 91229712}
    checkpoint = source / 'checkpoints/91229712'; checkpoint.mkdir(parents=True)
    freestyle.atomic_json(checkpoint / 'FREESTYLE_COMPLETE.json', complete)
    freestyle.atomic_json(checkpoint / 'FREESTYLE_STATE.json', {**complete, 'initialization': 'RANDOM_FROM_SCRATCH'})
    (checkpoint / 'POLICY.lt').write_bytes(b'preserved-parent-actor')
    identity['binary_sha256'] = 'new-build'
    return SimpleNamespace(source=source, checkpoint=checkpoint, identity=identity)


def tree_contents(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_fork_uses_last_complete_actor_and_never_changes_parent(parent):
    before = tree_contents(parent.source)
    incomplete = parent.source / 'checkpoints/99999999'; incomplete.mkdir()
    (incomplete / 'POLICY.lt').write_bytes(b'incomplete-newer-model')
    settings = freestyle.revised_reward_settings('overnight')
    folder = freestyle.fork_policy('rewards02', 'overnight', settings)
    assert (folder / 'parent_policy/POLICY.lt').read_bytes() == b'preserved-parent-actor'
    assert all(tree_contents(parent.source)[name] == content for name, content in before.items())
    protocol = freestyle.read_json(folder / 'protocol.json')
    assert protocol['initialization'] == 'policy_continuation'
    assert protocol['parent_policy']['parent_update'] == 2612
    assert protocol['identity']['binary_sha256'] == 'new-build'
    assert protocol['settings']['native']['actor_lr'] == .00005
    assert protocol['settings']['native']['critic_warmup_updates'] == 10
    assert not list((folder / 'checkpoints').glob('*'))


@pytest.mark.parametrize('problem', ['same_run', 'architecture', 'schema', 'incomplete'])
def test_bad_continuation_refused_before_creating_new_run(parent, problem):
    settings = freestyle.revised_reward_settings('overnight')
    if problem == 'architecture': settings['native']['width'] = 1024
    if problem == 'schema':
        protocol = freestyle.read_json(parent.source / 'protocol.json')
        protocol['identity']['backend_sha']['FreestyleObs.h'] = 'different-input-meaning'
        freestyle.atomic_json(parent.source / 'protocol.json', protocol)
    if problem == 'incomplete':
        (parent.checkpoint / 'FREESTYLE_STATE.json').write_text('{"schema":1,"update":2611}')
    with pytest.raises(ValueError):
        freestyle.fork_policy('overnight' if problem == 'same_run' else 'rewards02', 'overnight', settings)
    assert not freestyle.run_path('rewards02').exists()


def test_prepared_fork_launches_warm_start_then_resumes_its_own_checkpoints(parent, tmp_path, monkeypatch):
    folder = freestyle.fork_policy('rewards02', 'overnight', freestyle.revised_reward_settings('overnight'))
    binary = tmp_path / 'SlaterFreestyleNative'; binary.write_text('stub')
    monkeypatch.setattr(freestyle, 'binary_path', lambda folder=None: binary)
    monkeypatch.setattr(native_setup, 'meshes', lambda: tmp_path / 'meshes')
    monkeypatch.setattr(native_setup, 'runtime_environment', lambda *args: {})
    monkeypatch.setattr(freestyle, 'WandbMonitor', lambda *args: SimpleNamespace(state={}, close=lambda: None, submit=lambda event: None))
    launches = []

    def spawn(args, **kwargs):
        launches.append(list(args))
        kwargs['stdout'].write(b'FREESTYLE_COMPLETE {"status":"COMPLETE","updates":1,"timesteps":1024}\n')
        kwargs['stdout'].flush()
        return SimpleNamespace(pid=5678, poll=lambda: 0)

    monkeypatch.setattr(freestyle.subprocess, 'Popen', spawn)
    freestyle.train('rewards02', freestyle.defaults(), resume=True, updates=1)
    assert '--warm-start' in launches[0] and '--resume' not in launches[0]
    checkpoint = folder / 'checkpoints/1024'; checkpoint.mkdir(parents=True)
    freestyle.atomic_json(checkpoint / 'FREESTYLE_COMPLETE.json', {'update': 1})
    freestyle.train('rewards02', freestyle.defaults(), resume=True, updates=1)
    assert '--resume' in launches[1] and '--warm-start' not in launches[1]


def test_interrupted_actor_copy_cannot_fall_back_to_random_initialization(parent, monkeypatch):
    def interrupted(*args):
        raise OSError('copy interrupted')

    monkeypatch.setattr(freestyle.shutil, 'copyfile', interrupted)
    with pytest.raises(OSError, match='copy interrupted'):
        freestyle.fork_policy('rewards02', 'overnight', freestyle.revised_reward_settings('overnight'))
    protocol = freestyle.read_json(freestyle.run_path('rewards02') / 'protocol.json')
    assert protocol['initialization'] == 'policy_continuation_pending'
    with pytest.raises(RuntimeError, match='refusing random initialization'):
        freestyle.train('rewards02', freestyle.defaults(), resume=True)
