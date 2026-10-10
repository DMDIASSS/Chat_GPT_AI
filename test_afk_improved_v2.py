"""Unit tests for AFK Improved v2. No RocketSim, internet, or GPU required."""
import argparse
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import download_ballchasing as dl
from afk_v2_device import validate_device


class FakeClient:
    def __init__(self, ids):
        self.ids=ids
        self.fetched=[]
        self.lock=threading.Lock()
    def get(self,url,binary=False):
        if binary:
            with self.lock:self.fetched.append(url)
            return b'\x23' * 512
        if url.startswith(dl.API_ROOT+'replays?'):
            return {'list':[{'id':rid,'playlist_id':'ranked-duels','visibility':'public'} for rid in self.ids], 'next':None}
        raise RuntimeError('Unexpected URL '+url)

class FakeBudget:
    def before_download(self):pass


def args(root,max_files=2,workers=2):
    return argparse.Namespace(max_files=max_files,page_size=50,hour_limit=180,workers=workers,
        output=root,playlist='ranked-duels',rank='gc-plus',after='2025-01-01',before='2026-10-09',
        from_ids=None,list_only=False,refresh_search=False,pause_file=root/'.pause')

class TestV2(unittest.TestCase):
    def test_pagination_resume_no_skipped_replays(self):
        with tempfile.TemporaryDirectory() as td:
            ids=[str(uuid.UUID(int=i+1)) for i in range(7)]
            fake=FakeClient(ids)
            opts=args(Path(td),max_files=2)
            for i in range(4):
                dl.run(opts,fake,FakeBudget())
                now=list((Path(td)/'ranked-duels').glob('*.replay'))
                self.assertEqual(len(now),min((i+1)*2,len(ids)))
            self.assertEqual(len(fake.fetched),7)
            self.assertEqual(len(set(fake.fetched)),7)
            state=list((Path(td)/'ranked-duels').glob('download_state_*.json'))[0]
            self.assertTrue(json.loads(state.read_text())['finished'])
    def test_pause_does_not_advance_page(self):
        with tempfile.TemporaryDirectory() as td:
            ids=[str(uuid.UUID(int=i+1)) for i in range(4)]
            fake=FakeClient(ids)
            opts=args(Path(td))
            opts.pause_file.parent.mkdir(parents=True,exist_ok=True)
            opts.pause_file.write_text('pause')
            dl.run(opts,fake,FakeBudget())
            self.assertEqual(len(fake.fetched),0)
            state=list((Path(td)/'ranked-duels').glob('download_state_*.json'))[0]
            self.assertFalse(json.loads(state.read_text())['finished'])
            opts.pause_file.unlink()
            dl.run(opts,fake,FakeBudget())
            self.assertEqual(len(fake.fetched),2)
    def test_workers_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            a=args(Path(td),workers=4)
            with self.assertRaises(ValueError):dl.run(a,FakeClient([]),FakeBudget())
    def test_hourly_budget_thread_safe(self):
        with tempfile.TemporaryDirectory() as td:
            b=dl.HourlyBudget(Path(td)/'hours.json',hourly_limit=50)
            threads=[threading.Thread(target=b.before_download) for _ in range(10)]
            for t in threads:t.start()
            for t in threads:t.join(3);self.assertFalse(t.is_alive())
            self.assertEqual(len(json.loads((Path(td)/'hours.json').read_text())),10)
    def test_refresh_search_preserves_downloads_and_sees_new_ids(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            ids=[str(uuid.UUID(int=i+1)) for i in range(3)]
            fake=FakeClient(ids)
            opts=args(folder,max_files=0)
            dl.run(opts,fake,FakeBudget())
            self.assertEqual(len(fake.fetched),3)
            # First search finished; a normal resume must not fetch anything.
            fake.ids.append(str(uuid.UUID(int=4)))
            dl.run(opts,fake,FakeBudget())
            self.assertEqual(len(fake.fetched),3)
            opts.refresh_search=True
            dl.run(opts,fake,FakeBudget())
            self.assertEqual(len(fake.fetched),4)
            self.assertEqual(len(list((folder/'ranked-duels').glob('*.replay'))),4)

    def test_cpu_cuda_validation(self):
        validate_device('cpu',['cpu'])
        with self.assertRaises(ValueError):validate_device('cuda:0',['cpu'])
    def test_dark_inputs_and_hidden_launcher(self):
        root=Path(__file__).parent
        app=(root/'afk_improved_app.py').read_text()
        self.assertIn("sty.configure('TEntry',fieldbackground='#233245'",app)
        self.assertIn('self.jobs={}',app)
        self.assertIn("category='training'",app)
        self.assertIn("category='replay'",app)
        self.assertIn('subprocess.CREATE_NO_WINDOW',app)
        self.assertIn('pythonw.exe',(root/'AFK_IMPROVED_DESKTOP.vbs').read_text())
    def test_no_fake_multiplayer_claims(self):
        text=(Path(__file__).parent/'AFK_IMPROVED_TEAM_ROADMAP.md').read_text()
        self.assertIn('not implemented',text.lower())
        self.assertIn('1v3',text)

if __name__=='__main__':unittest.main(verbosity=2)
