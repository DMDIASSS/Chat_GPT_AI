import unittest
from rl_diagnostic_core import kickoff_quality, aggregate_kickoff_quality, kickoff_is_dangerous


def sample(*, a_distance=800., b_distance=2100., a_boost=20., b_boost=20.,
           a_gain=0., b_gain=0., ball_y_a=0., ball_vy_a=0., ball_x=0.):
    return {'ball_x': ball_x,
            'a': {'ball_distance': a_distance, 'boost_remaining': a_boost,
                  'boost_gained': a_gain, 'oriented_ball_y': ball_y_a,
                  'oriented_ball_vy': ball_vy_a},
            'b': {'ball_distance': b_distance, 'boost_remaining': b_boost,
                  'boost_gained': b_gain, 'oriented_ball_y': -ball_y_a,
                  'oriented_ball_vy': -ball_vy_a}}


class KickoffQualityTests(unittest.TestCase):
    def test_ball_control_win_without_a_goal(self):
        result = kickoff_quality(sample(), None)
        self.assertEqual(result['result'], 'ours')
        self.assertEqual(result['reason_a'], ['ball_control'])

    def test_relative_distance_matters(self):
        result = kickoff_quality(sample(a_distance=900, b_distance=700), None)
        self.assertEqual(result['result'], 'nexto')

    def test_safe_boost_pickup_qualifies_without_ball(self):
        result = kickoff_quality(sample(a_distance=2200, b_distance=2200,
                                        a_boost=55, a_gain=20), None)
        self.assertEqual(result['result'], 'ours')
        self.assertEqual(result['reason_a'], ['safe_boost_pickup'])

    def test_unchanged_boost_does_not_qualify(self):
        result = kickoff_quality(sample(a_distance=2200, b_distance=2200,
                                        a_boost=100, a_gain=0), None)
        self.assertEqual(result['result'], 'neutral')

    def test_boost_not_win_when_ball_threatens_own_goal(self):
        result = kickoff_quality(sample(a_distance=2500, b_distance=2000,
                                        a_boost=60, a_gain=60, ball_y_a=-4400), None)
        self.assertFalse(result['model_a_success'])
        self.assertNotIn('safe_boost_pickup', result['reason_a'])

    def test_fast_opponent_counter_is_dangerous(self):
        self.assertTrue(kickoff_is_dangerous(ball_x=0, oriented_ball_y=-1500,
                                            oriented_ball_vy=-900, my_distance=2200,
                                            opponent_distance=800))

    def test_both_boost_wins_marked_contested(self):
        result = kickoff_quality(sample(a_distance=2300, b_distance=2300,
                                        a_boost=65, b_boost=70,
                                        a_gain=40, b_gain=45), None)
        self.assertEqual(result['result'], 'contested')
        self.assertTrue(result['model_a_success'])
        self.assertTrue(result['model_b_success'])

    def test_early_goal_override(self):
        result = kickoff_quality(sample(), 'nexto')
        self.assertEqual(result['result'], 'nexto')
        self.assertEqual(result['reason_b'], ['early_goal'])
        self.assertFalse(result['model_a_success'])

    def test_goal_before_snapshot(self):
        result = kickoff_quality(None, 'ours')
        self.assertEqual(result['result'], 'ours')
        self.assertEqual(result['reason_a'], ['early_goal'])

    def test_missing_snapshot_neutral(self):
        self.assertEqual(kickoff_quality(None, None)['result'], 'neutral')

    def test_paired_aggregation(self):
        quality_a = kickoff_quality(sample(), None)
        quality_b = kickoff_quality(sample(a_distance=2300, b_distance=2300,
                                          a_boost=65, b_boost=70,
                                          a_gain=40, b_gain=45), None)
        row = {'sides':[{'kickoff_quality':quality_a}, {'kickoff_quality':quality_b}]}
        report = aggregate_kickoff_quality([row])
        self.assertEqual(report['exclusive_outcomes']['ours'], 1)
        self.assertEqual(report['exclusive_outcomes']['contested'], 1)
        self.assertAlmostEqual(report['kickoff_quality_score'], 0.75)
        self.assertAlmostEqual(report['model_a_quality_success_rate'], 1.)
        self.assertAlmostEqual(report['model_b_quality_success_rate'], .5)

if __name__ == '__main__':
    unittest.main()
