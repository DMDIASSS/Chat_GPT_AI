from pathlib import Path
import random

import numpy as np
import pytest
import torch

from afk_team_research import encode_multi
from slater_mechanics_eval import load_actor
from slater_team_env import FORMATS, TeamEnv, TeamObserver, goal_outcome, validate_format
from vendor.nexto.nexto_obs import NextoObsBuilder
import slater_cycle9_native_ppo_v025 as base

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def actor():
    torch.set_num_threads(1)
    return load_actor(ROOT, ROOT / 'vendor/nexto/nexto-model.pt')


def unpadded_observations(state, previous):
    encoded, ids = encode_multi(state)
    builder = NextoObsBuilder(n_players=len(ids), tick_skip=8)
    views = builder.batched_build_obs(encoded[None])
    result = {}
    for j, aid in enumerate(ids):
        builder.add_actions(views, previous.get(aid, np.zeros(8)), j)
        result[aid] = tuple(x[0].astype(np.float32) for x in views[j])
    return result


@pytest.mark.parametrize('format', FORMATS)
@pytest.mark.parametrize('side', ('blue', 'orange'))
def test_real_teams_exact_attention_contract_and_policy_controls(actor, format, side):
    ours, theirs = format
    env = TeamEnv({'nexto': actor}, our_size=ours, their_size=theirs,
                  fixed_side=side, max_seconds=.2)
    try:
        obs = env.reset(90210)
        assert len(env.state.cars) == ours + theirs
        assert len(env.clocks) == ours + theirs - 1
        assert len(env.our_ids) == ours and len(env.their_ids) == theirs
        assert env.ours in env.our_ids
        assert all(row['passed'] for row in env.observation_contract().values())
        views = env.observer.observe(env.state, {})
        unpadded = unpadded_observations(env.state, {})
        for aid, view in views.items():
            with torch.inference_mode():
                padded_logits = base.logits_of(actor, base.to_tensors(view))
                plain_logits = base.logits_of(actor, base.to_tensors(unpadded[aid]))
            torch.testing.assert_close(padded_logits, plain_logits, atol=1e-5, rtol=1e-5)
            n = len(env.state.cars)
            assert view[1].shape == (41, 24)
            assert np.all(view[1][n:6] == 0)
            assert np.all(view[2][n:6] == -10000)
            assert np.count_nonzero(view[2] == 0) == n + 35
            car = env.state.cars[aid]
            inversion = np.array([-1., -1., 1.]) if car.is_orange else np.ones(3)
            np.testing.assert_allclose(view[0][0, 5:8], car.physics.position * inversion / 2300, atol=1e-6)
        while True:
            with torch.inference_mode():
                action = int(base.logits_of(actor, base.to_tensors(obs)).argmax(-1).item())
            obs, reward, done, info = env.step(action)
            assert np.isfinite(reward)
            assert set(env.last_commands) == set(env.state.cars)
            for controls in env.last_commands.values():
                assert controls.shape == (8,)
                assert np.isfinite(controls).all() and np.max(np.abs(controls)) <= 1
            if done:
                break
        assert info['timeout'] and info['physics_ticks'] == 24
        assert info['student_script_physics_ticks'] == 0
        assert info['script_physics_ticks'] > 0
        assert env.frozen_observations == env.frozen_batch_calls * (ours + theirs - 1)
    finally:
        env.close()


def test_previous_inputs_and_reordered_roster_do_not_change_policy_views(actor):
    env = TeamEnv({'nexto': actor}, our_size=3, their_size=1, fixed_side='orange')
    try:
        env.reset(9421)
        previous = {aid: np.array([1, -.5, .2, -.1, .1, 0, 1, 0], np.float32) for aid in env.state.cars}
        original = env.observer.observe(env.state, previous)
        state = env.state
        state.cars = dict(reversed(list(state.cars.items())))
        reordered = TeamObserver().observe(state, previous)
        for aid in original:
            for left, right in zip(original[aid], reordered[aid]):
                np.testing.assert_array_equal(left, right)
            np.testing.assert_array_equal(reordered[aid][0][0, 24:], previous[aid])
    finally:
        env.close()


def test_swapped_teams_and_mirrored_physics_preserve_local_policy_view(actor):
    from nexto_teacher import INV, ROT180
    env = TeamEnv({'nexto': actor}, our_size=3, their_size=1, fixed_side='blue', task_name='ground')
    try:
        env.reset(5121)
        state = env.state
        original = env.observer.observe(state, {})
        state.ball.position = state.ball.position * INV
        state.ball.linear_velocity = state.ball.linear_velocity * INV
        state.ball.angular_velocity = state.ball.angular_velocity * INV
        ids = {}
        for aid, car in state.cars.items():
            car.team_num = 1 - car.team_num
            car.physics.position = car.physics.position * INV
            car.physics.linear_velocity = car.physics.linear_velocity * INV
            car.physics.angular_velocity = car.physics.angular_velocity * INV
            car.physics.rotation_mtx = ROT180 @ car.physics.rotation_mtx
            ids[aid] = ('orange-' if aid.startswith('blue-') else 'blue-') + aid.split('-')[1]
        state.cars = {ids[aid]: car for aid, car in state.cars.items()}
        # Boost pads are invariant as a complete set under this rotation. The
        # semantic car/ball vectors are compared after removing pad/car ordering.
        mirrored = TeamObserver().observe(state, {})
        for aid, (q, kv, mask) in original.items():
            mq, mkv, mmask = mirrored[ids[aid]]
            np.testing.assert_allclose(q, mq, atol=1e-6)
            original_car_tokens = sorted(map(tuple, np.round(kv[:len(ids)], 6)))
            mirrored_car_tokens = sorted(map(tuple, np.round(mkv[:len(ids)], 6)))
            np.testing.assert_allclose(original_car_tokens, mirrored_car_tokens, atol=1e-6)
            np.testing.assert_allclose(kv[6], mkv[6], atol=1e-6)
            # The vendored Nexto boost table contains one historical 3310/3308
            # coordinate discrepancy. Its fixed table is not exactly symmetric.
            # Match the rotated pad set and remove that <=2-unit table error
            # before asking for exact attention permutation invariance.
            distances = np.linalg.norm(kv[7:, None, 5:8] - mkv[None, 7:, 5:8], axis=-1)
            pad_pairs = distances.argmin(1)
            assert len(set(pad_pairs)) == 34
            assert float(distances[np.arange(34), pad_pairs].max()) <= 2.01 / 2300
            corrected = mkv.copy()
            corrected[7 + pad_pairs] = kv[7:]
            with torch.inference_mode():
                left = base.logits_of(actor, base.to_tensors((q, kv, mask)))
                right = base.logits_of(actor, base.to_tensors((mq, corrected, mmask)))
            torch.testing.assert_close(left, right, atol=3e-5, rtol=3e-5)
    finally:
        env.close()


@pytest.mark.parametrize('side', ('blue', 'orange'))
def test_team_goal_credit_from_actual_rocketsim_goal(actor, side):
    env = TeamEnv({'nexto': actor}, our_size=3, their_size=1, fixed_side=side, task_name='ground')
    try:
        env.reset(4211)
        sign = 1 if side == 'blue' else -1
        state = env.state
        state.ball.position = np.array([0., sign * 5050, 93.])
        state.ball.linear_velocity = np.array([0., sign * 1800, 0.])
        env.state = env.engine.set_state(state, {})
        env.potential = env.phi(env.state)
        outcome = 0
        for _ in range(12):
            _, reward, done, info = env.step(8)
            if done:
                outcome = info['outcome']
                assert reward > 9.
                break
        assert outcome == 1
        assert goal_outcome(env.state, env.ours) == 1
        assert info['learner_touch_ticks'] == 0  # Teammate/team goal credit, not touch credit.
    finally:
        env.close()


@pytest.mark.parametrize('task', ('teamplay', 'ground', 'defense', 'recovery', 'low_boost'))
def test_asymmetric_supporting_starts_and_global_rng_preservation(actor, task):
    env = TeamEnv({'nexto': actor}, our_size=1, their_size=3, fixed_side='orange', task_name=task, max_seconds=.1)
    try:
        before = random.getstate()
        obs = env.reset(4411)
        assert random.getstate() == before
        assert all(row['passed'] for row in env.observation_contract().values())
        while True:
            obs, reward, done, info = env.step(8)
            if done:
                break
        assert np.isfinite(reward)
        assert info['script_physics_ticks'] == 0
        assert info['format'] == '1v3'
    finally:
        env.close()


def test_invalid_rosters_and_controls_rejected(actor):
    for values in ((0, 1), (1, 4), (True, 2), (1., 2)):
        with pytest.raises(ValueError):
            validate_format(*values)
    with pytest.raises(ValueError):
        TeamEnv({'nexto': actor}, task_name='replay')
    env = TeamEnv({'nexto': actor})
    try:
        env.reset(111)
        for action in (-1, 90, 1.5):
            with pytest.raises(ValueError):
                env.step(action)
        with pytest.raises(ValueError):
            env.observer.observe(env.state, {env.ours: np.full(8, np.nan)})
    finally:
        env.close()


def test_evaluation_counts_every_goal_and_exact_match_clock(monkeypatch, actor):
    import slater_team_eval as evaluator
    resets = []

    class ThreeTickGoal:
        def __init__(self, rivals, **kwargs):
            self.max_seconds = kwargs['max_seconds']
            self.tick_count = 0

        def reset(self, seed):
            self.tick_count = 0
            resets.append(seed)
            return None

        def step(self, action):
            elapsed = min(3, round(self.max_seconds * 120) - self.tick_count)
            self.tick_count += elapsed
            return None, 10., True, {'outcome': 1, 'script_physics_ticks': 2}

        def close(self):
            pass

    monkeypatch.setattr(evaluator, 'TeamEnv', ThreeTickGoal)
    monkeypatch.setattr(evaluator, 'greedy', lambda actor, obs: 0)
    row = evaluator.match(actor, {'nexto': actor}, rival='nexto', side='orange', seed=5,
                          seconds=.1, our_size=1, their_size=3)
    assert row['seconds'] == .1 and row['episodes'] == 4
    assert row['goals_for'] == 4 and row['goals_against'] == 0
    assert row['script_physics_ticks'] == 8
    assert resets == [5, 5 + 7919, 5 + 2 * 7919, 5 + 3 * 7919]


def pair_record(fmt, side, seed, *, seconds=1., goals=0, conceded=0):
    ours, theirs = fmt
    row = {'format': f'{ours}v{theirs}', 'our_size': ours, 'their_size': theirs,
           'side': side, 'rival': 'nexto', 'seed': seed, 'seconds': seconds,
           'goals_for': goals, 'goals_against': conceded, 'goal_diff': goals - conceded,
           'student_scripted_kickoff': False, 'frozen_scripted_kickoff': True}
    return {'candidate': row, 'reference': {**row, 'goals_for': 0, 'goals_against': 0, 'goal_diff': 0}}


def test_paired_format_report_clusters_seeds_and_refuses_incomplete_cells():
    import copy
    from slater_team_eval import summarize
    formats = ((1, 1), (1, 3))
    rows = [pair_record(fmt, side, 500 + 997 * j, goals=int(fmt == (1, 1)), conceded=int(fmt == (1, 3)))
            for j in range(2) for fmt in formats for side in ('blue', 'orange')]
    kwargs = dict(formats=formats, rivals={'nexto': None}, seeds=2, seed_base=500, seconds=1.)
    result = summarize(rows, **kwargs)
    assert result['independent_seed_clusters'] == 2
    assert result['overall']['candidate']['matches'] == 8
    assert result['overall']['paired_goal_diff_per_minute']['mean'] == 0
    assert result['per_format']['1v1']['paired_goal_diff_per_minute']['mean'] == 60
    assert result['per_format']['1v3']['paired_goal_diff_per_minute']['mean'] == -60
    assert not result['confirmed'] and not result['promoted']
    with pytest.raises(ValueError, match='Incomplete'):
        summarize(rows[:-1], **kwargs)
    with pytest.raises(ValueError, match='Duplicate'):
        summarize(rows + rows[:1], **kwargs)
    mismatch = copy.deepcopy(rows)
    mismatch[0]['reference']['side'] = 'orange'
    with pytest.raises(ValueError, match='Unmatched'):
        summarize(mismatch, **kwargs)
    scripted = copy.deepcopy(rows)
    scripted[0]['candidate']['student_scripted_kickoff'] = True
    with pytest.raises(ValueError, match='kickoff mode'):
        summarize(scripted, **kwargs)


def test_evaluator_uses_same_frozen_reference_teammates_and_resume_identity(tmp_path, monkeypatch, actor):
    import slater_team_eval as evaluator
    calls = []
    reference = load_actor(ROOT, ROOT / 'vendor/nexto/nexto-model.pt')

    def fake_match(policy, rivals, **kwargs):
        calls.append((policy, kwargs['teammate_actor']))
        return pair_record((kwargs['our_size'], kwargs['their_size']), kwargs['side'], kwargs['seed'], seconds=.1)['candidate']

    monkeypatch.setattr(evaluator, 'match', fake_match)
    kwargs = dict(out=tmp_path / 'pairs.json', identity={'experiment': 'unit-fairness'},
                  formats=((1, 3), (3, 1)), seeds=2, seconds=.1, seed_base=100)
    result = evaluator.evaluate(actor, reference, {'nexto': actor}, **kwargs)
    assert result['done'] and len(result['records']) == 8
    assert len(calls) == 16 and all(teammate is reference for _, teammate in calls)
    evaluator.evaluate(actor, reference, {'nexto': actor}, **kwargs)
    assert len(calls) == 16
    with pytest.raises(ValueError, match='inputs, runtime or code changed'):
        evaluator.evaluate(actor, reference, {'nexto': actor}, **{**kwargs, 'scripted_student': True})


def test_actual_all_format_audit_preserves_source(actor, tmp_path):
    from slater_team_eval import audit
    from slater_v041_core import sha256
    source = ROOT / 'vendor/nexto/nexto-model.pt'
    digest = sha256(source)
    result = audit(source, out=tmp_path / 'contract.json', seed=810_000_000)
    assert result['passed'] and result['source_unchanged']
    assert len(result['records']) == 144
    assert sha256(source) == digest
    assert {row['phase'] for row in result['records']} == {'reset', 'after_controls'}
