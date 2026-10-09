"""Central configuration shared by training, replay imitation and deployment."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_ROOT = ROOT / "data" / "checkpoints" / "chat_gpt_ai"
DATASET_PATH = ROOT / "data" / "datasets" / "human_1v1.npz"
BOT_NAME = "Chat GPT AI"
TICK_SKIP = 8  # 120 physics ticks / 8 = 15 policy decisions per second.
POLICY_LAYERS = (512, 512)
CRITIC_LAYERS = (512, 512)

# Keep network, observation and action setup identical across all presets.
# Changing any of these invalidates old checkpoints / the bot runtime.
PRESETS = ("smoke", "fundamentals", "balanced", "mechanics", "competitive")


def recommended_workers(logical_cpus: int | None) -> int:
    """Conservative initial value. Benchmark throughput and tune it upward."""
    cpu = max(2, logical_cpus or 4)
    return max(2, min(24, cpu - 2))
