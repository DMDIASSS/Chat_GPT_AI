"""Checkpoint utilities. Uses same DiscreteFF class as RLGym-PPO."""
from pathlib import Path
import re
import numpy as np

from .config import CHECKPOINT_ROOT


def find_latest_policy(root: Path = CHECKPOINT_ROOT) -> Path:
    policies = list(Path(root).rglob('PPO_POLICY.pt'))
    if not policies:
        raise FileNotFoundError(f"No PPO_POLICY.pt under {root}. Train the bot first.")
    # Checkpoints are saved as cumulative timestep-numbered directories.
    return max(policies, key=lambda p: (int(p.parent.name) if p.parent.name.isdecimal() else -1, p.stat().st_mtime))


def policy_shape(weights: dict) -> tuple[int, tuple[int, ...], int]:
    # DiscreteFF is a Sequential under .model, Linear layers named .0/.2/.4 etc.
    layers = []
    for name, param in weights.items():
        m = re.fullmatch(r"model\.(\d+)\.weight", name)
        if m:
            layers.append((int(m.group(1)), tuple(param.shape)))
    layers.sort()
    if len(layers) < 2:
        raise ValueError("Checkpoint is not an RLGym-PPO DiscreteFF policy")
    input_dim = layers[0][1][1]
    hidden = tuple(shape[0] for _, shape in layers[:-1])
    output_dim = layers[-1][1][0]
    return input_dim, hidden, output_dim


class LoadedPolicy:
    def __init__(self, checkpoint: str | Path | None = None):
        import torch
        from rlgym_ppo.ppo.discrete_policy import DiscreteFF
        self.path = Path(checkpoint) if checkpoint else find_latest_policy()
        state = torch.load(str(self.path), map_location="cpu", weights_only=True)
        n_obs, layers, n_actions = policy_shape(state)
        self.policy = DiscreteFF(n_obs, n_actions, list(layers), device="cpu")
        self.policy.load_state_dict(state, strict=True)
        self.policy.eval()
        self.obs_count = n_obs
        self.action_count = n_actions

    def act(self, obs: np.ndarray) -> np.ndarray:
        import torch
        arr = np.asarray(obs, dtype=np.float32).reshape(-1)
        if len(arr) != self.obs_count:
            raise ValueError(f"Observation mismatch: checkpoint wants {self.obs_count}, got {len(arr)}")
        with torch.no_grad():
            distribution = self.policy.get_output(arr)
            idx = int(torch.argmax(distribution, dim=-1).item())
        return np.asarray([idx], dtype=np.int32)
