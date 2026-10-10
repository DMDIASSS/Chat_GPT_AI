from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('batch_fix', ROOT/'hub_fix_ppo_batch.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class BatchFixTests(unittest.TestCase):
    def setUp(self):
        self.original=(b'#include <GigaLearnCPP/Learner.h>\n// AFK_RESEARCH_HUB_PATCH_V1\n'
            b'int tsPerItr = HubInt("GL_HUB_STEPS_PER_ITER", 5000, 512, 200000);\n'
            b'cfg.ppo.tsPerItr = tsPerItr;\n'
            b'cfg.ppo.batchSize = tsPerItr;\n'
            b'cfg.ppo.miniBatchSize = std::min(tsPerItr, 2048);\n')
    def test_patch(self):
        out,changed=mod.patch_bytes(self.original)
        self.assertTrue(changed)
        self.assertIn(b'AFK_RESEARCH_HUB_PPO_BATCH_FIX_V1',out)
        self.assertIn(b'cfg.ppo.batchSize = tsPerItr;',out)
        self.assertIn(b'tsPerItr = (tsPerItr / hubMiniBatchSize) * hubMiniBatchSize;',out)
    def test_idempotent(self):
        out,changed=mod.patch_bytes(self.original)
        again,second=mod.patch_bytes(out)
        self.assertFalse(second)
        self.assertEqual(out,again)
    def test_reject_unknown(self):
        with self.assertRaises(RuntimeError):mod.patch_bytes(b'cfg.ppo.miniBatchSize = std::min(tsPerItr, 2048);')
    def test_batch_math(self):
        for req,expected in [(5000,4096),(4096,4096),(8192,8192),(2048,2048),(512,512),(3000,2048),(200000,198656)]:
            m=min(req,2048);actual=(req//m)*m
            self.assertEqual(expected,actual)
            self.assertEqual(0,actual%m)
    def test_core_defaults_and_encoding(self):
        s=(ROOT/'hub_core.py').read_text()
        self.assertIn("cfg.get('steps_per_iter',4096)",s)
        self.assertIn("'steps_per_iter':4096",s)
        self.assertIn("encoding='utf-8-sig'",s)
    def test_new_cpp_patch_produces_alignment(self):
        s=(ROOT/'hub_cpp_patch.py').read_text()
        self.assertIn('AFK_RESEARCH_HUB_PPO_BATCH_FIX_V1',s)
        self.assertIn('cfg.ppo.batchSize = tsPerItr;',s)

if __name__=='__main__':unittest.main()
