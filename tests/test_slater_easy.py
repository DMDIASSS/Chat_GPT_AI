"""No simulator, Torch, or Windows required for these local contract checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slater_easy
import slater_easy_monitor as monitor
import slater_transfer_diagnose as diagnose


class ContractTests(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(slater_easy.valid_name('first_1v1'), 'first_1v1')
        for unsafe in ('..', 'a/b', r'a\b', 'some name', '', 'x'*41):
            with self.assertRaises(ValueError):
                slater_easy.valid_name(unsafe)

    def test_command_argv_is_unquoted_path_parts(self):
        with patch.object(slater_easy, 'VENV', Path('C:/Program Files/Slater/.venv/python.exe')):
            args = slater_easy.cmd_for('run', run='abc',source=Path('C:/My Model/update180.pt'),
                                       config=Path('C:/My Config/config.json'))
        self.assertEqual(args[3], 'run')
        self.assertEqual(args[-4], '--source')
        self.assertEqual(args[-2], '--config')
        with self.assertRaises(ValueError):
            slater_easy.cmd_for('run', run='abc')

    def test_stock_lt_is_not_claimed_to_be_update180(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for name in diagnose.STOCK:
                (folder/name).write_text('placeholder')
            record=diagnose.describe_folder(folder)
            self.assertEqual(record['type'],'STOCK_GIGALEARN_SPLIT_ARCHIVE')
            self.assertIs(record['attention_transfer_verified'], False)
            audit=diagnose.make_report(folder/'missing_update180.pt',folder)
            self.assertIs(audit['transfer_verified'],False)
            self.assertEqual(audit['source']['status'],'PRIVATE_SOURCE_MISSING')

    def test_native_layout_only_provisionally_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for name in diagnose.ATTENTION|{'COMPLETE.json'}:
                (folder/name).write_text('placeholder')
            record=diagnose.describe_folder(folder)
            self.assertIsNone(record['attention_transfer_verified'])
            self.assertIn('NATIVE_ATTENTION',record['type'])

    def test_status_no_campaign_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(slater_easy,'CAMPAIGNS',Path(tmp)/'camp'),\
                 patch.object(slater_easy,'EASY',Path(tmp)/'easy'):
                current=slater_easy.status('missing')
                self.assertEqual(current['status'],'NOT_STARTED')
                self.assertEqual(current['promotions'],0)


class TelemetryTests(unittest.TestCase):
    def fake_campaign(self, folder, **kwargs):
        folder.mkdir(parents=True,exist_ok=True)
        state={'status':'TRAINING','phase':'training','cycle':1,'train_updates':20,
               'evaluation_games':4,'promotions':0,'routine':'match'}
        state.update(kwargs)
        (folder/'progress.json').write_text(json.dumps(state))
        (folder/'selected.json').write_text(json.dumps({'model_id':'id1'}))

    def test_no_events_without_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            m=monitor.Mirror('test',base/'out',mode='local')
            self.assertIs(m.poll(base/'missing'),False)
            self.assertFalse((base/'out'/'events.jsonl').exists())

    def test_idempotent_resume_and_measured_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);self.fake_campaign(base/'camp')
            m=monitor.Mirror('test',base/'out',mode='local')
            self.assertTrue(m.poll(base/'camp'))
            self.assertFalse(m.poll(base/'camp'))
            m2=monitor.Mirror('test',base/'out',mode='local')
            self.assertFalse(m2.poll(base/'camp'))
            self.fake_campaign(base/'camp',train_updates=40)
            self.assertTrue(m2.poll(base/'camp'))
            lines=(base/'out'/'events.jsonl').read_text().splitlines()
            self.assertEqual(len(lines),2)
            values=[json.loads(x) for x in lines]
            self.assertEqual([v['sequence'] for v in values],[1,2])
            self.assertEqual(values[1]['metrics']['campaign/train_updates'],40)
            self.assertNotIn('win_rate',str(values).lower())

    def test_sdk_failure_does_not_stop_progress(self):
        class Broken:
            def log(self,values,step):
                raise RuntimeError('do not print secret')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);self.fake_campaign(base/'camp')
            m=monitor.Mirror('test',base/'out',mode='local')
            m.run=Broken()
            self.assertTrue(m.poll(base/'camp'))
            self.assertEqual(m.state['last_sync_error'],'RuntimeError')
            self.assertNotIn('secret',str(m.state))

    def test_native_per_update_metrics_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            campaign = base / 'isolated/champion_campaigns/demo'
            native_dir = base / 'isolated/native_attention/runs/demo_c0001'
            self.fake_campaign(campaign, active={'run_name': 'demo_c0001', 'updates': 3})
            native_dir.mkdir(parents=True)
            (native_dir / 'progress.json').write_text(json.dumps({'updates': 3, 'decisions': 3072}))
            (native_dir / 'update_3.json').write_text(json.dumps({
                'update': 3, 'actor_loss': -0.01, 'rollout_policy_kl': 0.002,
                'overall_decisions_per_second': 900, 'source_api_key': 'SHOULD_NOT_LOG'}))
            data, identity = monitor.metrics_for('demo', campaign)
            self.assertEqual(data['native/updates'], 3)
            self.assertEqual(data['native/decisions'], 3072)
            self.assertEqual(data['native/rollout_policy_kl'], 0.002)
            self.assertNotIn('SHOULD_NOT_LOG', str(data))
            self.assertEqual(identity['native_update'], 3)

    def test_missing_auth_stays_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=monitor.Mirror('test',Path(tmp)/'mon',mode='local')
            self.assertFalse(m.connect())

    def test_invalid_monitor_id(self):
        with self.assertRaises(ValueError):
            monitor.safe_name('../danger')


if __name__=='__main__':
    unittest.main()
