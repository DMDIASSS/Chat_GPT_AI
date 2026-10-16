import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from imitation_metrics import ImitationMetrics

class LoggerTests(unittest.TestCase):
    def test_local_metrics_and_guardrails(self):
        with TemporaryDirectory() as temp:
            with ImitationMetrics(temp) as run:
                run.log(0, {'train/loss':1.0})
                run.log(2, {'val/loss': 0.5})
                with self.assertRaises(ValueError):
                    run.log(1, {'val/loss': 0.4})
                with self.assertRaises(ValueError):
                    run.log(3, {'val/loss':float('nan')})
            lines = (Path(temp)/'train_metrics.jsonl').read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[-1])['step'], 2)
    def test_mode_validation(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                ImitationMetrics(temp, wandb_mode='unknown')

if __name__ == '__main__':
    unittest.main()
