import tempfile
from pathlib import Path
import unittest
from rl_scenario_diagnostics import cache_key, read_cache, store_cache, selected_paths, parse


class CacheTests(unittest.TestCase):
    def test_cache_keys_isolate_weights_and_horizon(self):
        k1=cache_key('a','b','ground',5,750)
        self.assertNotEqual(k1,cache_key('c','b','ground',5,750))
        self.assertNotEqual(k1,cache_key('a','b','ground',5,90))
        self.assertNotEqual(k1,cache_key('a','b','wall',5,750))

    def test_corrupted_partial_line_doesnt_kill_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp=Path(tmp)/'cache.jsonl'
            store_cache(fp,'key1',{'score':1})
            with fp.open('a',encoding='utf-8') as out:
                out.write('{"broken":')
            store_cache(fp,'key2',{'score':2})
            self.assertEqual(read_cache(fp),{'key1':{'score':1},'key2':{'score':2}})

    def test_smoke_arguments(self):
        x=parse(['--smoke'])
        self.assertEqual((x.pairs,x.control_pairs,x.decisions),(1,1,90))

    def test_invalid_model_name(self):
        with self.assertRaises(ValueError):selected_paths(['champion=evil.pt'])


if __name__=='__main__':unittest.main()
