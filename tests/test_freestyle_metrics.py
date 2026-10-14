"""Monitoring must distinguish changing policy signals from fixed coefficients."""
from copy import deepcopy

import slater_freestyle as freestyle


def test_real_learning_changes_are_visible_beside_unchanged_reward_coefficients():
    first = {'update': 12, 'timesteps': 400000, 'metrics': {
        'Policy Loss': -.3, 'Critic Loss': .8, 'Policy Entropy': .72,
        'Post-update PPO KL': .015, 'Policy Update Magnitude': .12,
        'Average Step Reward': .002, 'weights': {'wall_pop': 1.1}}}
    second = deepcopy(first)
    second['update'] = 13
    second['metrics'].update({'Policy Loss': -.1, 'Critic Loss': .4,
                             'Policy Update Magnitude': .07})
    a, b = map(freestyle.flatten_metrics, (first, second))
    assert a['metrics/weights/wall_pop'] == b['metrics/weights/wall_pop'] == 1.1
    assert a['learning/actor_loss'] == -.3 and b['learning/actor_loss'] == -.1
    assert a['learning/critic_loss'] == .8 and b['learning/critic_loss'] == .4
    assert a['learning/actor_parameter_change_l2'] == .12
    assert b['learning/actor_parameter_change_l2'] == .07
    assert a['learning/policy_kl_after_update'] == .015


def test_missing_or_incomplete_evaluation_is_not_recorded_as_zero_success():
    for evaluation in (None, {'complete': False, 'episodes': 2, 'success_rate': .5}):
        result = freestyle.flatten_metrics({'update': 1, 'metrics': {}, 'evaluation': evaluation})
        assert not any(key.startswith('validation/') for key in result)
        assert 'learning/actor_loss' not in result
        assert 'practice/success_rate' not in result


def test_completed_evaluation_records_real_zero_events_and_per_episode_rates():
    event = {'update': 10, 'metrics': {'outcomes': {'episodes/contact_pop': 4,
        'successes/contact_pop': 3}, 'reward_components': {'weighted_sum/wall_pop': 2.2}},
        'evaluation': {'complete': True, 'episodes': 16, 'successes': 8, 'success_rate': .5,
            'telemetry': {'events/air_touch': 32, 'measurements/best_carry_seconds_sum': 8}}}
    result = freestyle.flatten_metrics(event)
    assert result['practice/success_rate'] == .75
    assert result['reward_contributions/wall_pop'] == 2.2
    assert result['validation/success_rate'] == .5
    assert result['validation/air_touches_per_episode'] == 2
    assert result['validation/mean_best_carry_seconds'] == .5
    assert result['validation/goals_per_episode'] == 0
    assert result['validation/resets_per_episode'] == 0


def test_invalid_metrics_cannot_become_plot_values():
    event = {'update': 1, 'metrics': {'Policy Loss': float('nan'),
             'Critic Loss': float('inf'), 'Post-update PPO KL': True}}
    result = freestyle.flatten_metrics(event)
    assert not any(key.startswith('learning/') for key in result)
