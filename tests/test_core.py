from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import numpy as np

from chatgpt_ai.config import recommended_workers, POLICY_LAYERS
from chatgpt_ai.curriculum_config import DISTRIBUTIONS, choose_scenario
from chatgpt_ai.math_utils import facing_matrix, safe_unit
from chatgpt_ai.policy import find_latest_policy, policy_shape


def test_presets_probabilities():
    for key, items in DISTRIBUTIONS.items():
        assert abs(sum(p for _, p in items) - 1.0) < 1e-9, key
        assert choose_scenario(key) in [name for name, _ in items]


def test_direction_and_facing():
    assert np.allclose(safe_unit([0, 0, 0]), 0)
    m = facing_matrix(np.array([10, 2, 4]))
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-7)
    assert np.linalg.det(m) > .99


def test_workers():
    assert recommended_workers(2) == 2
    assert recommended_workers(12) == 10
    assert recommended_workers(128) == 24


def test_checkpoint_shape_and_search():
    import torch
    model_weights = {
        'model.0.weight': torch.zeros(512, 92),
        'model.2.weight': torch.zeros(512, 512),
        'model.4.weight': torch.zeros(90, 512),
    }
    assert policy_shape(model_weights) == (92, POLICY_LAYERS, 90)
    with TemporaryDirectory() as d:
        for n in [100, 1000]:
            path = Path(d) / str(n) / 'PPO_POLICY.pt'
            path.parent.mkdir(parents=True)
            path.touch()
        assert find_latest_policy(Path(d)).parent.name == '1000'
