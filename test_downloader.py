import argparse
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from download_ballchasing import search_url, load_ids, run, valid_url, HourlyBudget


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, binary=False):
        self.calls.append((url, binary))
        if binary:
            return b'fake replay bytes'
        return {
            'list': [
                {'id': '67b6d4ff-b47c-4a1f-bf3d-c233a2c6ae24', 'playlist_id': 'ranked-duels', 'visibility': 'public'},
                {'id': 'bd8b2460-d199-455a-bb11-a9239c55bd3d', 'playlist_id': 'ranked-duels', 'visibility': 'public'},
            ],
            'next': None,
        }


class TestDownloader(unittest.TestCase):
    def test_exact_search_url(self):
        q = parse_qs(urlsplit(search_url('all', 'gc3-ssl', 150)).query)
        self.assertEqual(q['playlist'], ['ranked-duels', 'ranked-doubles', 'ranked-solo-standard', 'ranked-standard'])
        self.assertEqual(q['min-rank'], ['grand-champion-3'])
        self.assertEqual(q['max-rank'], ['supersonic-legend'])

    def test_broad_search_url(self):
        q = parse_qs(urlsplit(search_url('ranked-duels', 'gc-plus', 50)).query)
        self.assertEqual(q['min-rank'], ['grand-champion'])
        self.assertNotIn('max-rank', q)

    def test_manifest(self):
        p = Path(__file__).parent/'saved_page_replay_ids.txt'
        self.assertEqual(len(load_ids(p)), 150)

    def test_url_guard(self):
        for url in ['https://evil.test/api/replays', 'http://ballchasing.com/api/replays', 'https://ballchasing.com/']:
            with self.assertRaises(ValueError):
                valid_url(url)

    def test_download_resume_skips_files(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            args = argparse.Namespace(from_ids=None, output=dest, max_files=50,
                                      page_size=150, hour_limit=180, playlist='ranked-duels',
                                      rank='gc-plus', list_only=False)
            client = FakeClient()
            budget = HourlyBudget(dest/'.attempts.json')
            self.assertEqual(run(args, client, budget), 2)
            self.assertEqual(len(list((dest/'ranked-duels').glob('*.replay'))), 2)
            self.assertEqual(run(args, client, budget), 0)
            self.assertEqual(len(list((dest/'ranked-duels').glob('*.replay'))), 2)


if __name__ == '__main__':
    unittest.main()
