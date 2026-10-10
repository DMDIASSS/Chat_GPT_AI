"""No RocketSim/Torch needed: safety and protocol tests."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import afk_improved_core as core
import afk_improved_runner as runner
import afk_replay_audit as audit

class TestAfkImproved(unittest.TestCase):
    def test_json_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'nested'/'file.json'
            core.atomic_json(p,{'x':1})
            self.assertEqual(core.read_json(p)['x'],1)
            self.assertFalse(p.with_name('file.json.tmp').exists())

    def test_export_requires_data_path(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(core,'ROOT',Path(td)),patch.object(core,'DATA',Path(td)/'data'/'afk_improved'):
                secret=Path(td)/'secret.pt';secret.write_bytes(b'no')
                with self.assertRaises(ValueError):core.safe_copy_selected('secret.pt')
                source=Path(td)/'data'/'models'/'good.pt';source.parent.mkdir(parents=True)
                source.write_bytes(b'fake checkpoint bytes')
                out=core.safe_copy_selected('data/models/good.pt')
                self.assertEqual(out.read_bytes(),source.read_bytes())
                self.assertEqual(core.safe_copy_selected('data/models/good.pt'),out)
                self.assertEqual(source.read_bytes(),b'fake checkpoint bytes')

    def test_protected_starting_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);orig=base/'data'/'autoleague';orig.mkdir(parents=True)
            main=orig/'champion.pt';main.write_bytes(b'main')
            state=orig/'league_state.json';core.atomic_json(state,{'champion_sha':core.hash_file(main)})
            c9=orig/'cycle09.pt';c9.write_bytes(b'cycle9')
            patches=[patch.object(core,'CYCLE9',c9),patch.object(core,'CYCLE9_SHA',core.hash_file(c9)),
                     patch.object(core,'MAIN_CHAMPION',main),patch.object(core,'MAIN_STATE',state)]
            for item in patches:item.start()
            try:
                before=core.verify_starting_files()
                core.verify_untouched(before)
                main.write_bytes(b'mutated')
                with self.assertRaises(RuntimeError):core.verify_untouched(before)
            finally:
                for item in patches:item.stop()

    def test_backup_is_checksum_verified(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);a=base/'a.pt';b=base/'league_state.json'
            a.write_bytes(b'abc');b.write_text('{}')
            with patch.object(core,'DATA',base/'data'/'afk_improved'):
                out=core.checkpoint_snapshot((a,b))
                manifest=json.loads((out/'MANIFEST.json').read_text())
                self.assertEqual(len(manifest),2)
                self.assertEqual(a.read_bytes(),b'abc')
                self.assertEqual(core.hash_file(a),manifest[0]['sha256'])

    def test_integrity_of_verified_best(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);c9=base/'source.pt';c9.write_bytes(b'hello')
            with patch.object(core,'CYCLE9',c9),patch.object(core,'DATA',base/'data'),\
                 patch.object(core,'BEST',base/'data'/'best_verified.pt'),\
                 patch.object(core,'BEST_STATE',base/'data'/'best_verified.json'),\
                 patch.object(core,'LEAGUE',base/'data'/'league'):
                self.assertTrue(core.init_best());self.assertFalse(core.init_best())
                self.assertTrue(core.existing_checkpoint_verified())
                core.BEST.write_bytes(b'corrupted')
                self.assertFalse(core.existing_checkpoint_verified())
                with self.assertRaises(RuntimeError):core.init_best()

    def test_runner_config_rejects_bad_values(self):
        import argparse
        args=argparse.Namespace(cycles=0,hours=-1,eval_games=40,segment_decisions=8192,rollout=512)
        with self.assertRaises(ValueError):runner.validate(args)

    def test_replay_audit_deduplicates(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);(base/'x').mkdir()
            (base/'x'/'a.replay').write_bytes(b'\x01'*200)
            (base/'x'/'b.replay').write_bytes(b'\x01'*200)
            result=audit.audit(base)
            self.assertEqual(result['unique_binary_hashes'],1)
            self.assertEqual(result['file_count'],2)
            self.assertFalse(result['training_ready'])

    def test_download_filter_date(self):
        import download_ballchasing
        query=download_ballchasing.search_url('ranked-duels','gc-plus',50,'2024-01-01','2026-10-09')
        self.assertIn('replay-date-after=2024-01-01T00%3A00%3A00Z',query)
        self.assertIn('replay-date-before=2026-10-09T23%3A59%3A59Z',query)
        self.assertIn('ranked-duels',query)

if __name__=='__main__':unittest.main(verbosity=2)
