import importlib.util
from pathlib import Path
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('msvc_patch', BASE/'apply_msvc_hotfix.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

class HotfixTests(unittest.TestCase):
    def test_known_original_header(self):
        original=Path('/mnt/data/frozen_bridge_build/GigaLearn_Project/Research_Hub/Frozen_Opponents/FrozenNextoBridge.h')
        if not original.is_file(): self.skipTest('Source unavailable')
        a=original.read_text()
        b=patch.fix_text(a)
        self.assertNotIn('env.numActions',b)
        self.assertIn('payloadShape',b)
        self.assertIn('GetActionAmount() != 90',b)
        self.assertEqual(patch.fix_text(b),b)

    def test_installer_backup_and_second_apply(self):
        original=Path('/mnt/data/frozen_bridge_build/GigaLearn_Project/Research_Hub/Frozen_Opponents/FrozenNextoBridge.h')
        if not original.is_file(): self.skipTest('Source unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths=[root/'local/FrozenNextoBridge.h',root/'installed/FrozenNextoBridge.h']
            for p in paths:
                p.parent.mkdir(parents=True)
                p.write_bytes(original.read_bytes())
            patch.apply(paths)
            after=[p.read_bytes() for p in paths]
            for p in paths:
                self.assertEqual(p.with_name('FrozenNextoBridge.h.before_msvc_fix_v1.bak').read_bytes(),original.read_bytes())
            patch.apply(paths)
            self.assertEqual(after,[p.read_bytes() for p in paths])

    def test_unexpected_file_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            p=root/'a/FrozenNextoBridge.h';p.parent.mkdir()
            q=root/'b/FrozenNextoBridge.h';q.parent.mkdir()
            source=Path('/mnt/data/frozen_bridge_build/GigaLearn_Project/Research_Hub/Frozen_Opponents/FrozenNextoBridge.h')
            if not source.is_file(): self.skipTest('Source unavailable')
            p.write_bytes(source.read_bytes());q.write_text('unfamiliar')
            with self.assertRaises(ValueError):patch.apply([p,q])
            self.assertEqual(p.read_bytes(),source.read_bytes())

if __name__=='__main__': unittest.main()
