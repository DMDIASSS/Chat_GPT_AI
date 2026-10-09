"""Small in-memory engine integration test. Does not claim real RocketSim parity."""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexto_teacher import nexto_actions
from test_teacher import fake_state


def test_collect_rollout_shards_with_fake_engine(tmp_path, monkeypatch):
    class FakeEngine:
        def __init__(self, *args, **kwargs):
            self.step_count = 0
        def create_base_state(self):
            st = fake_state()
            st.tick_count = 0
            return st
        def set_state(self, state, shared):
            return state
        def step(self, actions, shared):
            self.step_count += 8
            assert set(actions) == {1, 2}
            assert all(v.shape == (8, 8) for v in actions.values())
            state = self.state
            state.tick_count += 8
            return state
        def close(self):
            pass

    class Engine(FakeEngine):
        def set_state(self, state, shared):
            self.state = state
            return state

    class Mutator:
        def __init__(self, *args, **kwargs):
            pass
        def apply(self, state, shared):
            pass

    class FakeObs:
        def reset(self, agents, state, shared):
            pass
        def build_obs(self, agents, state, shared):
            return {k: np.full((92,), k * 0.01 + state.tick_count * 0.0001, dtype=np.float32) for k in agents}

    modules = {}
    for name in [
        'rlgym', 'rlgym.rocket_league', 'rlgym.rocket_league.sim',
        'rlgym.rocket_league.action_parsers', 'rlgym.rocket_league.state_mutators',
        'chatgpt_ai', 'chatgpt_ai.env', 'chatgpt_ai.curriculum',
    ]:
        modules[name] = types.ModuleType(name)
    modules['rlgym.rocket_league.sim'].RocketSimEngine = Engine
    modules['rlgym.rocket_league.action_parsers'].LookupTableAction = type(
        'LookupTableAction', (), {'make_lookup_table': staticmethod(nexto_actions)})
    modules['rlgym.rocket_league.state_mutators'].FixedTeamSizeMutator = Mutator
    modules['rlgym.rocket_league.state_mutators'].KickoffMutator = Mutator
    modules['chatgpt_ai.curriculum'].ChatGPTCurriculum = Mutator
    modules['chatgpt_ai.env'].make_obs = FakeObs
    for key, value in modules.items():
        monkeypatch.setitem(sys.modules, key, value)

    from collect_nexto_rollouts import run
    args = SimpleNamespace(teacher_device='cpu', scenarios='grounded', output=tmp_path,
         max_decisions=6, episode_decisions=2, save_every=4, temperature=1., random_action_rate=0.)
    run(args)
    paths = sorted(tmp_path.glob('nexto_rollout_*.npz'))
    assert len(paths) == 3
    with np.load(paths[0]) as a:
        assert a['obs'].shape == (4, 92)
        assert a['teacher_probs'].shape == (4, 90)
        assert np.allclose(a['teacher_probs'].astype(np.float32).sum(1), 1, atol=2e-3)
    from inspect_nexto_dataset import inspect
    inspect(tmp_path)
