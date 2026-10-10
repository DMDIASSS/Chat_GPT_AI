import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guard_fix', HERE/'fix_dll_build_guard.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ZIP=Path('/mnt/data/Chat_GPT_AI_GigaLearn_Frozen_Nexto_Rotation_Bridge_v1.zip')

class TestGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with ZipFile(ZIP) as z:
            cls.original=z.read('GigaLearn_Project/Research_Hub/Frozen_Opponents/frozen_cli.py').decode()
    def test_patches_and_compiles(self):
        src=mod.change(self.original)
        self.assertIn('FROZEN_DLL_BUILD_GUARD_V1',src)
        self.assertIn("EXECUTABLE.with_name('GigaLearnCPP.dll')",src)
        compile(src,'frozen_cli.py','exec')
    def test_idempotence(self):
        src=mod.change(self.original)
        self.assertEqual(src,mod.change(src))
    def test_backup_and_repeat_install(self):
        with tempfile.TemporaryDirectory() as t:
            target=Path(t)/'frozen_cli.py'; backup=Path(t)/'orig.bak'
            target.write_text(self.original)
            self.assertTrue(mod.install(target,backup))
            self.assertFalse(mod.install(target,backup))
            self.assertEqual(backup.read_text(),self.original)
    def test_rejects_unknown(self):
        with self.assertRaises(RuntimeError):mod.change('def verify_install():\n    pass\n\ndef preflight():\n    pass\n')
    def test_dll_markers(self):
        s=mod.change(self.original)
        self.assertIn('GL_FROZEN_STOP_AFTER_STEPS',s)
        self.assertIn('GigaLearnCPP.dll lacks frozen teacher code',s)

if __name__=='__main__':unittest.main()
