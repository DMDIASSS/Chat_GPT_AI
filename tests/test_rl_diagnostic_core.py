import unittest
from rl_diagnostic_core import generate_plan, aggregate_pair_rows, paired_difference, interval, KINDS


def row(scenario, seed, outcomes=('ours','nexto'), *, fingerprint='state'):
    return {'scenario': scenario,'seed': seed, 'sides': [
        {'orange':False,'outcome':outcomes[0],'fingerprint':fingerprint,
         'decisions':12,'touches_a':2,'touches_b':3},
        {'orange':True,'outcome':outcomes[1],'fingerprint':fingerprint,
         'decisions':20,'touches_a':4,'touches_b':3},
    ]}


class TestDiagnosticCore(unittest.TestCase):
    def test_plan_deterministic_and_contains_every_category(self):
        a=generate_plan(442,5)
        self.assertEqual(a,generate_plan(442,5))
        self.assertEqual(set(a),set(KINDS))
        self.assertEqual([len(x) for x in a.values()],[5]*len(KINDS))
        self.assertNotEqual(a,generate_plan(443,5))
        long=generate_plan(442,30)
        for kind in KINDS:
            self.assertEqual(a[kind], long[kind][:5])

    def test_aggregate_pair_scores_and_sides(self):
        result=aggregate_pair_rows([row('ground',1,('ours','ours')),
                                     row('ground',2,('nexto','draw'))])
        self.assertEqual(result['episodes'],4)
        self.assertEqual(result['outcomes'],{'ours':2,'nexto':1,'draw':1})
        self.assertAlmostEqual(result['score'],(1+.25)/2)
        self.assertEqual(result['decisions'],64)
        self.assertEqual(result['paired_initial_state_mismatches'],0)

    def test_paired_diff_no_unmatched(self):
        a=[row('ground',1,('ours','ours')),row('ground',2,('draw','draw'))]
        b=[row('ground',1,('nexto','nexto')),row('ground',2,('draw','draw'))]
        d=paired_difference(a,b,seed=9)
        self.assertEqual(d['paired_starts'],2)
        self.assertAlmostEqual(d['score_difference'],.5)

    def test_duplicate_or_bad_sides_rejected(self):
        r=row('ground',9)
        r['sides'][1]['orange']=False
        with self.assertRaises(ValueError):aggregate_pair_rows([r])

    def test_mismatches_tracked(self):
        r=row('defense',17)
        r['sides'][1]['fingerprint']='different'
        self.assertEqual(aggregate_pair_rows([r])['paired_initial_state_mismatches'],1)

    def test_bootstrap_bounds(self):
        low, high=interval([.25,.5,.75]*5,seed=8,resamples=300)
        self.assertLessEqual(low,.5)
        self.assertGreaterEqual(high,.5)


if __name__ == '__main__':unittest.main()
