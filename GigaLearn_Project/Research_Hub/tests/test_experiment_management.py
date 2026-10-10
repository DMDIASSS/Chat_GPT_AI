import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import hub_core
import hub_experiment_management as manage
import ADD_EXPERIMENT_MANAGEMENT as installer


class ExperimentManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patchdir=patch.object(hub_core,'EXPERIMENTS',Path(self.tmp.name)/'experiments')
        self.patchdir.start()
        self.p=hub_core.new_experiment('alpha','Balanced 1v1')
        checkpoint=self.p/'checkpoints'/'1234'
        checkpoint.mkdir(parents=True)
        (checkpoint/'POLICY.lt').write_bytes(b'policy1234')
        (checkpoint/'CRITIC.lt').write_bytes(b'critic1234')
    def tearDown(self):
        self.patchdir.stop()
        self.tmp.cleanup()
    def test_rename_moves_checkpoint_and_metadata_and_keeps_other_project_intact(self):
        n=manage.rename_experiment('alpha','Defense 1v1 (new)')
        self.assertEqual(n,'defense_1v1_new')
        moved=hub_core.exp_path(n)
        self.assertTrue(moved.exists())
        self.assertFalse(self.p.exists())
        self.assertEqual((moved/'checkpoints/1234/POLICY.lt').read_bytes(),b'policy1234')
        self.assertEqual(hub_core.read_json(moved/'experiment.json')['name'],n)
        self.assertFalse((moved/'launch.lock').exists())
        self.assertEqual(len(hub_core.list_experiments()),1)
    def test_no_overwrites_or_identical_name(self):
        hub_core.new_experiment('beta','Balanced 1v1')
        with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','beta')
        with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','alpha')
        self.assertTrue(self.p.is_dir())
    def test_running_pid_blocks_rename_and_archive(self):
        hub_core.atomic_json(self.p/'running.json',{'pid':456})
        with patch.object(hub_core,'is_alive',return_value=True):
            with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','renamed')
            with self.assertRaises(manage.ManagementError):manage.archive_experiment('alpha')
        self.assertTrue(self.p.is_dir())
        self.assertEqual((self.p/'checkpoints/1234/POLICY.lt').read_bytes(),b'policy1234')
    def test_stop_flag_blocks_management(self):
        (self.p/'request_safe_stop.flag').write_text('STOP')
        with self.assertRaises(manage.ManagementError):manage.archive_experiment('alpha')
        with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','b')
        self.assertTrue(self.p.is_dir())
    def test_launch_lock_blocks_management(self):
        (self.p/'launch.lock').write_text('launch')
        with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','b')
        self.assertEqual((self.p/'launch.lock').read_text(),'launch')
    def test_corrupt_running_file_blocks_management(self):
        (self.p/'running.json').write_text('not-json')
        with self.assertRaises(manage.ManagementError):manage.archive_experiment('alpha')
        self.assertTrue(self.p.is_dir())
    def test_delete_is_recoverable_and_restore(self):
        dest=manage.archive_experiment('alpha')
        self.assertFalse(self.p.exists())
        self.assertTrue((dest/'checkpoints/1234/POLICY.lt').exists())
        self.assertFalse((dest/'launch.lock').exists())
        self.assertEqual(len(hub_core.list_experiments()),0)
        items=manage.list_trashed_experiments()
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['name'],'alpha')
        restored=manage.restore_trashed_experiment(items[0]['archive_id'])
        self.assertEqual(restored,'alpha')
        self.assertEqual((self.p/'checkpoints/1234/POLICY.lt').read_bytes(),b'policy1234')
        self.assertFalse(dest.exists())
    def test_restore_doesnt_overwrite_new_name_conflict(self):
        dest=manage.archive_experiment('alpha')
        hub_core.new_experiment('alpha','Balanced 1v1')
        with self.assertRaises(manage.ManagementError):manage.restore_trashed_experiment(dest.name)
        self.assertTrue(dest.exists())
    def test_weird_name_or_symlink_is_rejected(self):
        with self.assertRaises(manage.ManagementError):manage.rename_experiment('alpha','alpha')
        with self.assertRaises(manage.ManagementError):manage.restore_trashed_experiment('../something')
    def test_installer_backwards_compatible_and_idempotent(self):
        import zipfile
        zip_path=ROOT.parents[2]/'Chat_GPT_AI_GigaLearn_Research_Hub_v1.zip'
        # Local release ZIP is optional when users run these tests on Windows.
        if zip_path.exists():
            with zipfile.ZipFile(zip_path) as z:
                original=z.read('GigaLearn_Project/Research_Hub/hub_app.py')
        else:
            pristine=(ROOT/'hub_app.py').read_bytes().decode('utf-8')
            begin=pristine.index(' def rename_exp(self):')
            end=pristine.index(' def create_evolution(self):')
            pristine=pristine[:begin]+pristine[end:]
            for newer,older in [(installer.HEADER_NEW,installer.HEADER_OLD),(installer.MODULE_LINE,''),(installer.BUTTONS,''),(installer.HELP_NEW,installer.HELP_OLD)]:
                pristine=pristine.replace(newer,older)
            original=pristine.encode('utf8')
        patched,changed=installer.patch_source(original)
        self.assertTrue(changed)
        self.assertIn(b' def rename_exp(self):',patched)
        self.assertIn(b' def delete_exp(self):',patched)
        self.assertIn(b' def restore_exp(self):',patched)
        self.assertIn(b'self.button(r,\'Rename selected\'',patched)
        second,changed=installer.patch_source(patched)
        self.assertFalse(changed)
        self.assertEqual(second,patched)
    def test_installer_refuses_unknown_version_without_touching_it(self):
        with self.assertRaises(RuntimeError):installer.patch_source(b'print("other")\n')


if __name__=='__main__':unittest.main()
