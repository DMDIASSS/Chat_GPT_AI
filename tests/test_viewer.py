import importlib.util
import sys
import tempfile
from pathlib import Path
import unittest
import types
from unittest import mock

import numpy as np

PATH = Path(__file__).resolve().parents[1] / 'watch_latest_ai.py'
spec = importlib.util.spec_from_file_location('watch_latest_ai', PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class ViewerTests(unittest.TestCase):
    def touch(self, p):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'test')
        return p

    def test_latest_ppo_is_highest_step_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self.touch(root / 'data/checkpoints/chat_gpt_ai/250000/PPO_POLICY.pt')
            b = self.touch(root / 'data/checkpoints/chat_gpt_ai/1000050/PPO_POLICY.pt')
            a.touch()  # Deliberately newer mtime for older checkpoint
            self.assertEqual(m.latest_ppo(root).path, b)

    def test_auto_excludes_smoke_and_original_nexto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.touch(root / 'vendor/nexto/nexto-model.pt')
            self.touch(root / 'data/checkpoints/chat_gpt_ai_smoke_backup/100000/PPO_POLICY.pt')
            with self.assertRaises(FileNotFoundError):
                m.choose_model(root, 'auto')

    def test_student_v2_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = self.touch(root / 'data/nexto_student_policy.pt')
            p2 = self.touch(root / 'data/nexto_student_v2.pt')
            self.assertEqual(m.choose_model(root, 'student').path, p2)
            self.assertNotEqual(p1, p2)

    def test_auto_selects_most_recent_trained_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.touch(root / 'data/checkpoints/chat_gpt_ai/1000050/PPO_POLICY.pt')
            selected = self.touch(root / 'data/nexto_student_v2.pt')
            self.assertEqual(m.choose_model(root, 'auto').path, selected)

    def test_model_override_recognizes_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self.touch(root / 'data/native_nexto/last.pt')
            self.assertEqual(m.choose_model(root, 'auto', str(p)).family, 'native')

    def test_action_probability_validation(self):
        rng = np.random.default_rng(101)
        probs = np.arange(1, 91, dtype=np.float64)
        self.assertEqual(m.sample_action(probs, rng, 'greedy'), 89)
        self.assertIn(m.sample_action(probs, rng, 'sample'), range(90))
        with self.assertRaises(ValueError):
            m.sample_action(np.ones(89), rng, 'sample')
        with self.assertRaises(ValueError):
            m.sample_action(np.full(90, np.nan), rng, 'sample')

    def test_native_actor_real_logits_match_original(self):
        # Test unmodified Nexto TorchScript inference via the same observation
        # layout used by the Fast Track pipeline. No RocketSim required.
        import torch
        archive = Path('/mnt/data/Chat_GPT_AI_Fast_Track')
        if not (archive/'vendor/nexto/nexto-model.pt').exists():
            self.skipTest('original Nexto model not mounted')
        sys.path.insert(0, str(archive))
        # Make a temporary project containing the same files NativeController expects.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'vendor/nexto').mkdir(parents=True)
            import shutil
            shutil.copyfile(archive/'vendor/nexto/nexto-model.pt', root/'vendor/nexto/nexto-model.pt')
            for name in ('original_agent.py','nexto_obs.py'):
                shutil.copyfile(archive/'vendor/nexto'/name, root/'vendor/nexto'/name)
            with mock.patch.object(m, 'ROOT', root):
                actor = m.NativeController(m.ModelChoice('nexto', root/'vendor/nexto/nexto-model.pt'))
                teacher = torch.jit.load(str(root/'vendor/nexto/nexto-model.pt'), map_location='cpu')
                q = torch.zeros((1, 1, 32), dtype=torch.float32)
                kv = torch.zeros((1, 37, 24), dtype=torch.float32)
                mask = torch.zeros((1, 37), dtype=torch.float32)
                with torch.inference_mode():
                    left, _ = actor.actor((q, kv, mask))
                    right, _ = teacher((q, kv, mask))
                self.assertTrue(torch.equal(left, right))

    def test_inference_only_and_both_car_controls(self):
        # Simulated game engine/visualizer to verify the 1v1 loop without
        # claiming that physical RocketSim is installed in this runtime.
        from types import SimpleNamespace
        from contextlib import ExitStack
        base = 'rlgym.rocket_league'
        modules = {name: types.ModuleType(name) for name in
                   ('rlgym',base,base+'.sim',base+'.rlviser',base+'.action_parsers')}
        class DummyEngine:
            def __init__(self, **kwargs):
                self.closed = False
            def step(self, commands, _):
                assert len(commands) == 2
                assert all(v.shape == (8,8) for v in commands.values())
                self.count += 1
                return SimpleNamespace(cars={1:SimpleNamespace(is_orange=False, ball_touches=1),
                                             2:SimpleNamespace(is_orange=True, ball_touches=0)},
                                       goal_scored=self.count >= 2,
                                       ball=SimpleNamespace(position=np.array([0, 500, 0])))
            def close(self):
                self.closed = True
        class DummyRender:
            def __init__(self, **kwargs): self.closed = False
            def render(self, *_): pass
            def close(self): self.closed = True
        class DummyPolicy:
            def __init__(self, *_): self.table = np.zeros((90,8),dtype=np.float32)
            def reset(self, _): pass
            def actions(self, state, *_): return {k:np.ones(8,dtype=np.float32) for k in state.cars}
        obj = DummyEngine()
        obj.count = 0
        modules[base+'.sim'].RocketSimEngine = lambda **kwargs: obj
        modules[base+'.rlviser'].RLViserRenderer = DummyRender
        modules[base+'.action_parsers'].LookupTableAction = type('LookupTableAction', (), {})
        def kickoff(_engine, _start, _rng):
            return SimpleNamespace(cars={1:SimpleNamespace(is_orange=False),2:SimpleNamespace(is_orange=True)},
                                   goal_scored=False,ball=SimpleNamespace(position=np.array([0,0,0])))
        with ExitStack() as stack:
            for key, val in modules.items():
                stack.enter_context(mock.patch.dict(sys.modules, {key:val}))
            stack.enter_context(mock.patch.object(m,'FFController', DummyPolicy))
            stack.enter_context(mock.patch.object(m,'create_state',kickoff))
            stack.enter_context(mock.patch.object(m.time,'sleep',lambda *_:None))
            m.run_view(m.ModelChoice('student',Path('dummy.pt')), 'sample','kickoff',1.0,5,1,123,0)
            self.assertTrue(obj.closed)
            self.assertEqual(obj.count,2)

if __name__ == '__main__':
    unittest.main()
