import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fetch_ranked_doubles import acceptable_replay, safe_page_url, previous_ids

class FetchTests(unittest.TestCase):
    def test_safe_next(self):
        self.assertTrue(safe_page_url('https://ballchasing.com/api/replays?after=abc'))
        self.assertFalse(safe_page_url('https://example.net/api/replays'))
        self.assertFalse(safe_page_url('http://ballchasing.com/api/replays'))
        self.assertFalse(safe_page_url('https://ballchasing.com/api/replays/abc/file'))
        self.assertFalse(safe_page_url('https://ballchasing.com.evil.net/api/replays'))
    def test_doubles_only(self):
        match = {'playlist_id':'ranked-doubles', 'duration':300,
                 'blue': {'players':[{},{}]}, 'orange': {'players':[{},{}]}}
        self.assertTrue(acceptable_replay(match, 90))
        match['orange']['players'] = [{}]
        self.assertFalse(acceptable_replay(match, 90))
        match['orange']['players'] = [{},{}]
        match['playlist_id'] = 'ranked-duels'
        self.assertFalse(acceptable_replay(match, 90))
        match['playlist_id'] = 'ranked-doubles'
        match['duration'] = 30
        self.assertFalse(acceptable_replay(match, 90))
    def test_manifest_resume_only_existing_files(self):
        with TemporaryDirectory() as temp:
            d=Path(temp)
            (d/'ok.replay').write_bytes(b'X'*200)
            manifest = d/'download_manifest.jsonl'
            with manifest.open('w') as f:
                f.write(json.dumps({'status':'downloaded','id':'good','rocket_league_id':'RL1','file':'ok.replay'})+'\n')
                f.write(json.dumps({'status':'downloaded','id':'missing','rocket_league_id':'RL2','file':'none.replay'})+'\n')
            ids, rlids = previous_ids(manifest)
            self.assertEqual(ids, {'good'})
            self.assertEqual(rlids, {'RL1'})

if __name__ == '__main__':
    unittest.main()
