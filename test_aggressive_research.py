import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import afk_aggressive_research as r

class TestResearch(unittest.TestCase):
    def test_distinct_variants(self):
        self.assertEqual(len(set(x[0] for x in r.VARIANTS)),len(r.VARIANTS))
        self.assertEqual([x[1] for x in r.VARIANTS],sorted(x[1] for x in r.VARIANTS))
        self.assertTrue(r.VARIANTS[-1][1]>=20*r.VARIANTS[0][1])

    def test_preflight_missing_checkpoint_refuses(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(FileNotFoundError):r.preflight(Path(t),idle=False)

    def test_verdict_promising_and_failed(self):
        entry=lambda score,starts:{'score':score,'unique_starts':starts,'outcomes':{'ours':30,'nexto':15,'draw':5}}
        a={'candidate_vs_nexto':entry(.60,50),'champion_vs_nexto':entry(.51,50),
           'candidate_vs_champion':entry(.55,50),'games':100}
        self.assertEqual(r.decide_score(a)['status'],'promising_for_longer_test')
        a['candidate_vs_champion']['score']=.45
        self.assertEqual(r.decide_score(a)['status'],'unproven_or_regressed')
        a['candidate_vs_champion']['score']=.60;a['candidate_vs_nexto']['unique_starts']=2
        self.assertEqual(r.decide_score(a)['status'],'unproven_or_regressed')

    def test_previous_afk_cycle9_detection(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);folder=root/'data'/'afk_improved'/'league'/'inconclusive'
            folder.mkdir(parents=True)
            a=folder/'old_cycle0009.pt';a.write_bytes(b'a')
            with patch.object(r,'ROOT',root):
                self.assertEqual(r.optional_prior_candidate(),a)
                b=folder/'other_cycle0009.pt';b.write_bytes(b'b')
                with self.assertRaises(RuntimeError):r.optional_prior_candidate()

    def test_branch_requires_unambiguous_candidate(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(r,'BASE',Path(t)):
                self.assertRaises(RuntimeError,lambda:r.branch_candidate('control'))

    def test_branch_skip_resume(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(r,'BASE',Path(t)):
                folder=r.variant_dir('control');(folder/'inconclusive').mkdir(parents=True)
                saved=folder/'inconclusive'/'x_cycle0001.pt';saved.write_bytes(b'original')
                r.atomic_json(folder/'league_state.json',{'cycle':2})
                with patch.object(r.subprocess,'Popen',side_effect=AssertionError('Cannot restart complete branch')):
                    self.assertEqual(r.execute_branch('control',3e-6,.6,.1,.001,steps=8192,seed=1,training_games=40),saved)
                self.assertEqual(saved.read_bytes(),b'original')

    def test_pause_has_no_weights(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(r,'BASE',Path(t)),patch.object(r,'PAUSE',Path(t)/'pause.request'):
                self.assertEqual(r.cli(['pause']),0)
                self.assertTrue((Path(t)/'pause.request').exists())
                self.assertEqual(list(Path(t).glob('*.pt')),[])

    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'x'/'z.json';r.atomic_json(path,{'ok':True})
            self.assertEqual(json.loads(path.read_text()),{'ok':True})
            self.assertFalse((path.parent/(path.name+'.partial')).exists())

if __name__=='__main__':unittest.main()
