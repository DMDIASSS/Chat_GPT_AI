"""Native policy and public API contract regressions. No real games required."""
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import download_ballchasing as dl
from afk_device_safety import choose_device,check_cpu_policy,hardcoded_cpu_ops

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'vendor'/'nexto'/'nexto-model.pt'

class TestNativeNextoDevice(unittest.TestCase):
    @unittest.skipUnless(MODEL.exists(),'Copy project vendor/nexto directory to test TorchScript probe')
    def test_real_pretrained_actor_on_cpu(self):
        self.assertIn('OK',check_cpu_policy(MODEL))
    @unittest.skipUnless(MODEL.exists(),'Copy project vendor/nexto directory to test JIT code')
    def test_constant_cpu_in_jit(self):
        import torch
        actor=torch.jit.load(str(MODEL),map_location='cpu')
        self.assertTrue(hardcoded_cpu_ops(actor))
    @unittest.skipUnless(MODEL.exists(),'Copy project vendor/nexto directory to test CUDA protection')
    def test_cuda_requested_but_jit_is_cpu_fixed(self):
        with patch('torch.cuda.is_available',return_value=True):
            device,note=choose_device('cuda:0',MODEL)
        self.assertEqual(device,'cpu')
        self.assertIn('SAFE FALLBACK',note)
    def test_cpu_is_selected_safely(self):
        self.assertEqual(choose_device('cpu',Path('unused'))[0],'cpu')

class TestBallchasingDocumentedAPI(unittest.TestCase):
    def test_documented_rank_dates(self):
        params=parse_qs(urlsplit(dl.search_url('ranked-duels','gc-plus',50,'2025-01-01','2026-10-09')).query)
        self.assertEqual(params['min-rank'],['grand-champion'])
        self.assertEqual(params['replay-date-after'],['2025-01-01T00:00:00Z'])
        self.assertEqual(params['replay-date-before'],['2026-10-09T23:59:59Z'])
        self.assertNotIn('replay-after',params)
    def test_invalid_ssl_filter_is_rejected_explicitly(self):
        with self.assertRaisesRegex(ValueError,'NOT documented'):
            dl.search_url('ranked-duels','gc3-ssl',50)

if __name__=='__main__':unittest.main(verbosity=2)
