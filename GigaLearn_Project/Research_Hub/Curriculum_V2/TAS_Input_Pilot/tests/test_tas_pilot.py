import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'tas_pilot.py'
spec = importlib.util.spec_from_file_location('tas_pilot', MODULE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def sample(path, n=30, invalid=False):
    d = bytearray(struct.pack('<II', 1, n))
    for i in range(n):
        d += struct.pack('<I7f', 12, 0.25, -0.75, 0, 0, 1, 0, 0)
    tail=bytearray(128)
    struct.pack_into('<3f', tail, 12, 100, -500, 50)
    struct.pack_into('<3f', tail, 64, 0, 0, 93)
    d += tail
    if invalid:d.pop()
    path.write_bytes(d)

class TestTAS(unittest.TestCase):
    def test_sample(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'test.data';sample(f)
            c=p.load_tas(f)
            self.assertEqual(c['frames'], 30)
            self.assertEqual(c['candidate_initial_car_xyz'],[100.,-500.,50.])
            self.assertEqual(c['candidate_initial_ball_xyz'],[0.,0.,93.])
            self.assertFalse(c['candidate_state_verified'])
    def test_bad_length(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'broken.data';sample(f,invalid=True)
            with self.assertRaises(p.TASFormatError):p.load_tas(f)
    def test_dedupe(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);sample(root/'a.data');sample(root/'b.data')
            clips,errors=p.scan(root)
            self.assertEqual((len(clips),len(errors)),(1,0))
    def test_plan_never_executes(self):
        with tempfile.TemporaryDirectory() as t:
            dst=Path(t)/'plan.json'
            r=p.opponent_plan(dst,2,5)
            self.assertTrue(r['must_build_native_pt_opponent_bridge'])
            self.assertEqual([i['teacher'] for i in r['schedule']], ['Nexto','Cycle 9','Wavedash']*2)
            with self.assertRaises(FileExistsError):p.opponent_plan(dst)
    def test_train_gates(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);sample(root/'a.data')
            with self.assertRaises(p.TASFormatError):p.fit(root,root/'out',epochs=3)
            with self.assertRaises(ValueError):p.fit(root,root/'out',epochs=0)

if __name__=='__main__':unittest.main()
