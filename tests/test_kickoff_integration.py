"""Small mocked physics tests for the kickoff telemetry integration.

These validate control flow only; a Windows RocketSim smoke test is still needed.
"""
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

import rl_scenario_diagnostics as diag


class FakeCar:
    def __init__(self, is_orange, pos, boost):
        self.is_orange = is_orange
        self.physics = types.SimpleNamespace(position=np.array(pos, dtype=float))
        self.boost_amount = boost


class FakeMatch:
    def __init__(self, *, goal_step=None):
        self.ours = 'ours'
        self.opponent = 'opponent'
        self.state = types.SimpleNamespace(
            ball=types.SimpleNamespace(position=np.array([0., -1600., 93.]),
                                       linear_velocity=np.array([0., -700., 0.])),
            cars={
                'ours': FakeCar(False, [2500, -3500, 17], 20.),
                'opponent': FakeCar(True, [0, -1600, 17], 20.)
            }
        )
        self.decisions = 0
        self.contacts = {'ours': 0, 'nexto': 0}
        self.goal_step = goal_step

    def observe(self):
        return ('own_view', 'opp_view')

    def step(self, _a, _b, max_decisions):
        self.decisions += 1
        # The opponent gets a boost pad at tick 20, but gets scored on later.
        if self.decisions == 20:
            self.state.cars['opponent'].boost_amount = 75.
        if self.goal_step == self.decisions:
            return 0, True, 'ours'
        return 0, self.decisions >= max_decisions, 'draw'


class KickoffIntegrationTests(unittest.TestCase):
    def test_oriented_snapshot_matches_each_team(self):
        match = FakeMatch()
        snapshot = diag.kickoff_state_snapshot(match, {'a': 12, 'b': 18})
        self.assertEqual(snapshot['a']['oriented_ball_y'], -1600)
        self.assertEqual(snapshot['b']['oriented_ball_y'], 1600)
        self.assertEqual(snapshot['a']['oriented_ball_vy'], -700)
        self.assertEqual(snapshot['b']['oriented_ball_vy'], 700)
        self.assertEqual(snapshot['b']['boost_gained'], 18)
        match.state.ball.position[1] = 1000
        self.assertEqual(snapshot['ball_x'], 0)
        self.assertEqual(snapshot['b']['oriented_ball_y'], 1600)

    def _simulate(self, *, goal_step=None, horizon=90):
        fake_module = types.ModuleType('auto_league')
        fake_module.action_greedy = lambda actor, view: 0
        fake_module.initial_fingerprint = lambda match: 'same_state'
        def factory(teacher, engine, orange, kind):
            return types.SimpleNamespace(match=FakeMatch(goal_step=goal_step))
        with patch.dict(sys.modules, {'auto_league': fake_module}):
            with patch.object(diag, 'DiagnosticMatch', side_effect=factory):
                return diag.simulate_pair(object(), object(), None, None,
                                          kind='kickoff', seed=122, decisions=horizon)

    def test_late_early_goal_overrides_opponent_boost_and_proximity(self):
        row = self._simulate(goal_step=85)
        for side in row['sides']:
            self.assertEqual(side['kickoff_quality']['result'], 'ours')
            self.assertEqual(side['kickoff_quality']['reason_a'], ['early_goal'])
            self.assertEqual(side['decisions'], 85)

    def test_no_early_goal_allows_boost_or_proximity_advantage(self):
        row = self._simulate(goal_step=None)
        for side in row['sides']:
            self.assertEqual(side['kickoff_quality']['result'], 'nexto')
            self.assertEqual(side['outcome'], 'draw')
            self.assertEqual(side['kickoff_quality']['reason_b'], ['ball_control', 'safe_boost_pickup'])

    def test_goal_before_snapshot_needs_no_snapshot(self):
        row = self._simulate(goal_step=25)
        for side in row['sides']:
            self.assertEqual(side['kickoff_quality']['result'], 'ours')
            self.assertFalse(side['kickoff_quality']['snapshot_available'])


if __name__ == '__main__':
    unittest.main()
