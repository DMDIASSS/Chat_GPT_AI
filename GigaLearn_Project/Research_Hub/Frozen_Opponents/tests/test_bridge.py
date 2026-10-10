import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import frozen_nexto_bridge as bridge
import frozen_cli
import install_bridge


class BridgeTest(unittest.TestCase):
    def test_lookup_90(self):
        tab = bridge.FrozenRotation._original_actions()
        self.assertEqual(tab.shape,(90,8))
        self.assertEqual(set(np.unique(tab[:, 5])),{0.,1.})
        self.assertTrue((np.isfinite(tab)).all())

    def test_flat_encoder(self):
        f=np.zeros(89,dtype=np.float32)
        f[:34]=1
        f[36]=93
        for b in (43,66):
            f[b+2]=17
            f[b+3]=f[b+7]=f[b+11]=1
            f[b+18]=33
            f[b+19]=f[b+20]=1
        s=bridge.encode_frame(f)
        self.assertEqual(s.shape,(131,))
        self.assertEqual(s[0:3].tolist(),[0.,0.,0.])
        self.assertEqual(s[37+2],93)
        self.assertEqual(s[3+34+18+1],0)

    def test_invalid_rotation_rejected(self):
        f=np.zeros(89,dtype=np.float32)
        with self.assertRaises(ValueError):bridge.encode_frame(f)

    def test_invalid_flat_rejected(self):
        with self.assertRaises(ValueError):bridge.encode_frame(np.zeros(90))
        f=np.zeros(89);f[2]=np.nan
        with self.assertRaises(ValueError):bridge.encode_frame(f)

    def test_patch_idempotent_and_student_only(self):
        source=Path('/mnt/data/Learner.cpp')
        if not source.exists():self.skipTest('Uploaded current source not mounted')
        original=source.read_text(encoding='utf-8-sig')
        result=install_bridge.patch(original)
        self.assertEqual(result,install_bridge.patch(result))
        self.assertIn('if (oldVersion || frozenBridge)',result)
        self.assertIn('int numRealPlayers = (oldVersion || frozenBridge)',result)
        self.assertIn('frozenBridge->Infer',result)
        self.assertIn('nexto',result)
        self.assertIn('cycle9',result)
        self.assertIn('wavedash',result)

    def test_patch_rejects_unknown_source(self):
        with self.assertRaises(ValueError):install_bridge.patch('int main(){return 0;}')

    def test_seed_creation_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);seed=t/'seed';seed.mkdir()
            for n in frozen_cli.MODEL_FILENAMES:
                if n=='RUNNING_STATS.json':(seed/n).write_text(json.dumps({'total_timesteps':120,'total_iterations':3}))
                else:(seed/n).write_bytes(b'fake-weights-'+n.encode())
            folder=t/'exp'
            orig=frozen_cli.EXPERIMENTS
            try:
                frozen_cli.EXPERIMENTS=folder
                class Args:pass
                a=Args();a.seed=str(seed);a.name='my_frozen_experiment'
                before=frozen_cli.filehash(seed/'POLICY.lt')
                frozen_cli.create(a)
                cp=folder/a.name/'checkpoints'/'0'
                self.assertEqual(before,frozen_cli.filehash(cp/'POLICY.lt'))
                self.assertEqual(json.loads((cp/'RUNNING_STATS.json').read_text())['total_timesteps'],0)
                self.assertEqual(json.loads((seed/'RUNNING_STATS.json').read_text())['total_timesteps'],120)
                with self.assertRaises(FileExistsError):frozen_cli.create(a)
            finally:frozen_cli.EXPERIMENTS=orig

    def test_installer_backups_real_source_in_temp_project(self):
        source=Path('/mnt/data/Learner.cpp')
        if not source.exists():self.skipTest('Uploaded source unavailable')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            target=root/'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
            header=root/'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Util/FrozenNextoBridge.h'
            a,b=install_bridge.LEARNER,install_bridge.HEADER
            try:
                install_bridge.LEARNER=target
                install_bridge.HEADER=header
                install_bridge.install()
                backup=target.with_name('Learner.cpp.before_frozen_nexto_bridge_v1.bak')
                self.assertEqual(backup.read_bytes(),source.read_bytes())
                self.assertIn('FROZEN_NEXTO_BRIDGE_V1',target.read_text())
                self.assertEqual(header.read_bytes(),(HERE/'FrozenNextoBridge.h').read_bytes())
                install_bridge.install()
                self.assertEqual(backup.read_bytes(),source.read_bytes())
            finally:
                install_bridge.LEARNER=a
                install_bridge.HEADER=b

    def test_bad_names_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            class Args:pass
            a=Args();a.seed=t;a.name='../oops'
            with self.assertRaises(ValueError):frozen_cli.create(a)

    def test_actual_actor_smoke_when_assets(self):
        import torch
        original=Path('/mnt/data/bridge_inspect/vendor/nexto/nexto-model.pt')
        cycle9=Path('/mnt/data/best_verified.pt')
        if not original.exists() or not cycle9.exists():self.skipTest('No native actor sample available')
        rot=bridge.FrozenRotation({'nexto':str(original),'cycle9':str(cycle9),
                                   'wavedash':str(cycle9)},bridge.FrozenRotation._original_actions())
        f=np.zeros((2,89),dtype=np.float32);f[:,:34]=1;f[:,36]=93
        for b in (43,66):
            f[:,b+2]=17;f[:,b+3]=f[:,b+7]=f[:,b+11]=1
            f[:,b+18]=33;f[:,b+19]=f[:,b+20]=1
        f[:,44]=-2400;f[:,67]=2400
        for n in ('nexto','cycle9','wavedash'):
            rot.select(n)
            vals=rot.infer(f,[0,1],True)
            self.assertEqual(len(vals),2)
            self.assertTrue(all(0<=v<90 for v in vals))

if __name__=='__main__':unittest.main()
