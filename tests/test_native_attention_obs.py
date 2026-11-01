"""Cross-language parity on nonzero real RocketSim states, not tensor stubs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from native_attention_obs_fixtures import real_states

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def obs_bridge(tmp_path_factory):
    explicit = os.environ.get('SLATER_ATTENTION_OBS_PARITY_BINARY')
    if explicit:
        executable = Path(explicit)
        assert executable.is_file(), f'Missing explicit parity executable: {executable}'
        return executable
    compiler = shutil.which('g++')
    candidates = [Path(os.environ.get('SLATER_GIGALEARN_SOURCE', '/missing')),
                  ROOT / 'data/isolated/gigalearn_native/source',
                  Path('/workspace/native-giga-test/upstream-source')]
    source = next((p for p in candidates if (p / 'GigaLearnCPP/RLGymCPP/src/RLGymCPP/CommonValues.h').is_file()), None)
    if not compiler or source is None:
        pytest.skip('Requires g++ and a patched pinned GigaLearn source, or SLATER_ATTENTION_OBS_PARITY_BINARY')
    executable = tmp_path_factory.mktemp('attention_obs_bridge') / 'SlaterAttentionObsParity'
    command = [compiler, '-std=c++20', '-O2', '-I', str(source / 'GigaLearnCPP/RLGymCPP/src'),
               '-I', str(source / 'GigaLearnCPP/libsrc/json'),
               str(ROOT / 'GigaLearn_Project/Native_Attention/ObsParity.cpp'), '-o', str(executable)]
    built = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert built.returncode == 0, built.stderr
    return executable


@pytest.fixture(scope='module')
def compared_states(obs_bridge, tmp_path_factory):
    directory = tmp_path_factory.mktemp('attention_obs_states')
    payload, expected = real_states()
    source, result = directory / 'states.json', directory / 'views.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    completed = subprocess.run([str(obs_bridge), str(source), str(result)], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    native = json.loads(result.read_text(encoding='utf-8'))['states']
    assert len(native) == len(expected) == len(payload['states']) == 108
    return payload, expected, native


def test_native_matches_original_attention_observations_all_rosters(compared_states):
    payload, expected, native = compared_states
    seen = set()
    views = 0
    for frame, python, cpp in zip(payload['states'], expected, native):
        assert frame['name'] == cpp['name']
        assert [row['agent_id'] for row in cpp['observations']] == list(python)
        roster = tuple(sum(car['is_orange'] == side for car in frame['cars']) for side in (False, True))
        seen.add(roster)
        for row in cpp['observations']:
            q, kv, mask = python[row['agent_id']]
            np.testing.assert_allclose(np.asarray(row['q'], np.float32).reshape(1, 32), q, rtol=0, atol=2e-6)
            np.testing.assert_allclose(np.asarray(row['kv'], np.float32).reshape(41, 24), kv, rtol=0, atol=2e-6)
            np.testing.assert_array_equal(np.asarray(row['mask'], np.float32), mask)
            views += 1
    assert seen == {(blue, orange) for blue in range(1, 4) for orange in range(1, 4)}
    assert views == 432  # Every player, so both learner colors are checked.


def test_fixture_contains_real_temporal_flags_and_nontrivial_features(compared_states):
    payload, expected, _ = compared_states
    cars = [car for state in payload['states'] for car in state['cars']]
    assert any(car['is_demoed'] for car in cars)
    assert any(car['has_double_jumped'] for car in cars)
    assert any(car['has_flipped'] for car in cars)
    assert any(car['air_time_since_jump'] > 1.25 for car in cars)
    assert any(not car['on_ground'] for car in cars)
    assert any(car['rotation_mtx'][2][2] < -.9 for car in cars)
    assert any(car['boost_amount'] == 0 for car in cars)
    assert any(any(timer > 1 for timer in state['boost_pad_timers']) for state in payload['states'])
    for views in expected:
        for q, kv, mask in views.values():
            assert np.count_nonzero(q) > 8
            assert np.all(kv[mask == -10000] == 0)


def test_native_obs_policy_logits_match_on_real_states(compared_states):
    import torch
    from slater_mechanics_eval import load_actor
    from native_nexto import actor_logits
    torch.set_num_threads(1)
    actor = load_actor(ROOT, ROOT / 'vendor/nexto/nexto-model.pt')
    _, expected, native = compared_states
    python_batch, cpp_batch = [], []
    for views, frame in zip(expected, native):
        for row in frame['observations']:
            python_batch.append(views[row['agent_id']])
            cpp_batch.append((np.asarray(row['q'], np.float32).reshape(1, 32),
                              np.asarray(row['kv'], np.float32).reshape(41, 24),
                              np.asarray(row['mask'], np.float32)))
    def batch(rows):
        return [torch.from_numpy(np.stack([row[i] for row in rows])) for i in range(3)]
    with torch.inference_mode():
        left, right = actor_logits(actor, *batch(python_batch)), actor_logits(actor, *batch(cpp_batch))
    assert torch.isfinite(right).all()
    torch.testing.assert_close(right, left, atol=2e-5, rtol=1e-5)
    assert torch.equal(right.argmax(-1), left.argmax(-1))


def test_native_obs_rejects_invalid_team_and_actions(obs_bridge, tmp_path):
    payload, _ = real_states()
    first = payload['states'][0]
    first['cars'][0]['previous'] = [2., 0, 0, 0, 0, 0, 0, 0]
    source, result = tmp_path / 'invalid.json', tmp_path / 'views.json'
    source.write_text(json.dumps({'states': [first]}), encoding='utf-8')
    completed = subprocess.run([str(obs_bridge), str(source), str(result)], capture_output=True, text=True)
    assert completed.returncode != 0
    assert 'Invalid attention previous controller input' in completed.stderr
