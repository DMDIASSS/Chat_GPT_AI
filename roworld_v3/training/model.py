"""CPU/GPU residual actor-critic, exactly mirrored by ../neural.lua."""
import json
from pathlib import Path
import torch
from torch import nn

SCHEMA = "roworld-observation-v1"
CONTEXT, ACTION, HIDDEN = 204, 48, 32


class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.context = nn.Linear(CONTEXT, HIDDEN)
        self.action = nn.Linear(ACTION, HIDDEN)
        self.fusion = nn.Linear(HIDDEN, HIDDEN)
        self.score = nn.Linear(HIDDEN, 1)
        self.value = nn.Linear(HIDDEN, 1)
        nn.init.zeros_(self.score.weight)
        nn.init.zeros_(self.score.bias)
        nn.init.zeros_(self.value.bias)

    def forward(self, context, actions, priors, mask):
        state = self.fusion(self.context(context).relu()).relu()
        tokens = self.action(actions).relu()
        logits = priors + (tokens * state[:, None, :]).sum(-1) / HIDDEN**0.5 + self.score(tokens).squeeze(-1)
        return logits.masked_fill(~mask, -1e9), self.value(state).squeeze(-1)

    def export(self):
        result = {"version": 1, "schema": SCHEMA, "parameters": sum(p.numel() for p in self.parameters())}
        for name in ("context", "action", "fusion", "score", "value"):
            layer = getattr(self, name)
            result[name] = {"w": layer.weight.detach().cpu().tolist(), "b": layer.bias.detach().cpu().tolist()}
        return result

    def save_json(self, path):
        Path(path).write_text(json.dumps(self.export(), separators=(",", ":"), allow_nan=False), encoding="utf8")

    def load_json(self, path):
        weights = json.loads(Path(path).read_text(encoding="utf8"))
        if weights.get("version") != 1 or weights.get("schema") != SCHEMA:
            raise ValueError("Only RoWorld v3 JSON weights are compatible")
        with torch.no_grad():
            for name in ("context", "action", "fusion", "score", "value"):
                layer = getattr(self, name)
                for key, parameter in (("w", layer.weight), ("b", layer.bias)):
                    value = torch.tensor(weights[name][key], dtype=parameter.dtype, device=parameter.device)
                    if value.shape != parameter.shape or not torch.isfinite(value).all():
                        raise ValueError("Bad model layer " + name)
                    parameter.copy_(value)


def batch(rows, device):
    n = max(len(r["candidates"]) for r in rows)
    context = torch.tensor([r["context"] for r in rows], dtype=torch.float32, device=device)
    actions = torch.zeros(len(rows), n, ACTION, device=device)
    priors = torch.zeros(len(rows), n, device=device)
    mask = torch.zeros(len(rows), n, dtype=torch.bool, device=device)
    for i, row in enumerate(rows):
        k = len(row["candidates"])
        actions[i, :k] = torch.tensor(row["candidates"], device=device)
        priors[i, :k] = torch.tensor(row["priors"], device=device)
        mask[i, :k] = True
    return context, actions, priors, mask
