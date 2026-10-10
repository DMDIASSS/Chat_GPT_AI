"""Regression tests for stale AFK run status and the real OS lock."""
import contextlib
import unittest
from unittest.mock import patch
from teamplay_v2 import no_simultaneous_afk, ROOT


class AFKLockGuardTests(unittest.TestCase):
    def test_live_lock_held_until_training_exits(self):
        transitions = []

        @contextlib.contextmanager
        def available_lock(path):
            self.assertEqual(path, ROOT / 'data' / 'autoleague')
            transitions.append('acquired')
            try:
                yield
            finally:
                transitions.append('released')

        with patch('auto_league.exclusive_league_lock', available_lock):
            with no_simultaneous_afk():
                self.assertEqual(transitions, ['acquired'])
            self.assertEqual(transitions, ['acquired', 'released'])

    def test_genuine_concurrent_autoleague_still_blocked(self):
        @contextlib.contextmanager
        def busy_lock(_):
            raise RuntimeError('Another AutoLeague is running for this data-dir')
            yield  # pragma: no cover

        with patch('auto_league.exclusive_league_lock', busy_lock):
            with self.assertRaisesRegex(RuntimeError, 'STILL holds the live training lock'):
                with no_simultaneous_afk():
                    self.fail('Should never reach training under a held lock')

    def test_unrelated_runtime_errors_are_not_swallowed(self):
        @contextlib.contextmanager
        def broken_lock(_):
            raise RuntimeError('Unexpected permission failure')
            yield  # pragma: no cover

        with patch('auto_league.exclusive_league_lock', broken_lock):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected permission failure'):
                with no_simultaneous_afk():
                    pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
