#!/usr/bin/env python3
"""Local JSONL metrics + optional W&B for any offline imitation trainer.

Keep the JSONL record even if W&B is offline. There are NO baked-in keys.
Integrate this helper with the training code that actually computes metrics;
logging alone is never evidence of model improvement.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Mapping


class ImitationMetrics:
    def __init__(self, directory: str | Path, *, project: str = "rocket-league-replay-imitation",
                 name: str | None = None, wandb_mode: str = "disabled",
                 config: Mapping | None = None):
        if wandb_mode not in {"disabled", "offline", "online"}:
            raise ValueError("wandb_mode must be disabled, offline or online")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log_file = self.directory / "train_metrics.jsonl"
        self.last_step = -1
        self.run = None
        if wandb_mode != "disabled":
            try:
                import wandb
            except ImportError as e:
                raise RuntimeError("Install W&B with: pip install wandb") from e
            # W&B reads credentials from `wandb login` or WANDB_API_KEY.
            # Offline mode works without a W&B sign-in.
            self.run = wandb.init(project=project, name=name, mode=wandb_mode,
                                  dir=str(self.directory), config=dict(config or {}),
                                  reinit="finish_previous")

    def log(self, step: int, metrics: Mapping[str, int | float]):
        if not isinstance(step, int) or step < 0 or step < self.last_step:
            raise ValueError("Metrics step must be a nonnegative monotonic integer")
        payload = {}
        for key, value in metrics.items():
            if not isinstance(key, str) or not key or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid metric: {key!r}={value!r}")
            if not math.isfinite(value):
                raise ValueError(f"Nonfinite metric {key}: {value}")
            payload[key] = float(value)
        record = {"step": step, **payload}
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if self.run is not None:
            self.run.log(payload, step=step)
        self.last_step = step

    def close(self):
        if self.run is not None:
            self.run.finish()
            self.run = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
