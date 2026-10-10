import importlib.util
import pathlib
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import tas_replay_link as mod
import install_reader as inst


def make_tas(p,n=400):
    # Stationary inputs, then slow alternation; stays within valid TAS v1 shape.
    with p.open('wb') as f:
        f.write(struct.pack('<II',1,n))
        for i in range(n):
            flags=0
            a=[0.,0.,0.,0.,0.,0.,0.]
            if i//32%2:a[0]=1.;a[1]=-1.;a[2]=1.
            f.write(struct.pack('<I7f',flags,*a))
        f.write(bytes(128))

def make_replay(p,n=150):
    with p.open('w',encoding='utf8') as f:
        f.write('GL_REPLAY_1\n')
        for i in range(n):
            # Action index with mostly zero control activity; cadence matches quiet TAS.
            arr=['0' for _ in range(53)]
            arr[0]=str(i//50);arr[1]=str(i%2);arr[2]='8'
            f.write(' '.join(arr)+'\n')

class LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.tas=self.root/'tas';self.tas.mkdir()
        make_tas(self.tas/'first.data');make_tas(self.tas/'second.data',375)
        self.ds=self.root/'replays';self.ds.mkdir()
        make_replay(self.ds/'replay_train.txt');make_replay(self.ds/'replay_val.txt',30)

    def test_native_action_table(self):
        self.assertEqual(len(mod.ACTIONS),90)
    def test_bad_header_safe(self):
        (self.tas/'bad.data').write_bytes(b'garbage')
        good,bad=mod.tas_clips(self.tas)
        self.assertEqual(len(good),2)
        self.assertEqual(bad[0]['file'],'bad.data')
    def test_link_no_fake_labels(self):
        out=self.root/'output'; r=mod.build(self.tas,self.ds,out)
        self.assertGreater(r['tas_replay_cadence_matching_rows'],0)
        self.assertEqual(r['replay_train_rows'],150)
        self.assertEqual(mod.sha(self.ds/'replay_val.txt'),mod.sha(out/'replay_val.txt'))
        with (out/'replay_train.txt').open() as f:
            self.assertEqual(f.readline().strip(),'GL_REPLAY_1')
            for line in f:
                parts=line.split();self.assertEqual(len(parts),54)
                self.assertGreaterEqual(float(parts[-1]),1.)
                self.assertLessEqual(float(parts[-1]),1.25)
        original=list(mod.read_replay_rows(self.ds/'replay_train.txt'))
        linked=(out/'replay_train.txt').read_text().splitlines()[1:]
        self.assertEqual([r[0] for r in original],[' '.join(x.split()[:53]) for x in linked])
        with self.assertRaises(FileExistsError):mod.build(self.tas,self.ds,out)
    def test_invalid_dataset(self):
        with (self.ds/'replay_train.txt').open('a') as f:f.write('0 1 4\n')
        with self.assertRaises(ValueError):mod.build(self.tas,self.ds,self.root/'bad_out')
    def test_patch_and_idempotence(self):
        src=self.root/'HubReplayBC.cpp'
        src.write_text('pfx\n'+inst.OLD_CHECK+'\n'+inst.OLD_WEIGHT+'\n',encoding='utf8')
        r=inst.patch(src)
        self.assertTrue(r['rebuild']);self.assertTrue(src.with_suffix('.cpp.before_tas_link_v1.bak').exists())
        self.assertFalse(inst.patch(src)['rebuild'])
        self.assertIn(inst.NEW_WEIGHT,src.read_text())
    def test_patch_rejects_unknown(self):
        src=self.root/'different.cpp';src.write_text('int main(){}')
        with self.assertRaises(RuntimeError):inst.patch(src)

if __name__=='__main__':unittest.main()

class OfflineInputTests(unittest.TestCase):
    def test_replay_prior_and_heldout_split(self):
        import train_controls_v2 as ti
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);tas=root/'tas';ds=root/'replays';tas.mkdir();ds.mkdir()
            for i in range(7):make_tas(tas/f'{i:02}.data',n=250+i*15)
            make_replay(ds/'replay_train.txt',n=180);make_replay(ds/'replay_val.txt',n=40)
            pr=ti.replay_prior(ds)
            self.assertGreater(len(pr),0)
            cl,_=mod.tas_clips(tas)
            train=ti.tensors(cl,list(range(6)),pr,stride=4,maxrows=400)
            held=ti.tensors(cl,[6],pr,stride=4,maxrows=400)
            self.assertEqual(train[0].shape[1],56)
            self.assertEqual(held[3].shape[1],9)
            self.assertGreater(len(held[0]),0)
