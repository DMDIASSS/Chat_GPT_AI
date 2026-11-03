"""Verified public Chronos V2.1 weights and AdvancedObsPadded(3) reference.

The reference consumes simulator truth when provided. Roblox pose/boost/jump
estimates are supplied by the existing adapter and remain estimates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch
from torch import nn

from bridge271 import PADS, lookup_table

APP = Path(__file__).resolve().parent
MANIFEST = json.loads((APP / "chronos_manifest.json").read_text())
ACTIONS = lookup_table()
MIRROR_PADS = [int(np.argmin(np.linalg.norm(PADS[:, :2] - p[:2] * [-1, 1], axis=1))) for p in PADS]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset_digest():
    return hashlib.sha256("".join(MANIFEST["files"].values()).encode("ascii")).hexdigest()


def verify_assets(folder):
    folder = Path(folder)
    for name, expected in MANIFEST["files"].items():
        if digest(folder / name) != expected:
            raise ValueError("Unrecognized Chronos asset: " + name)
    return folder


def download_assets(folder):
    """Fetch only the two pinned public inference archives, then verify hashes."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, expected in MANIFEST["files"].items():
        target = folder / name
        if target.is_file() and digest(target) == expected:
            continue
        temporary = target.with_suffix(".download")
        url = f'https://raw.githubusercontent.com/{MANIFEST["repository"]}/{MANIFEST["revision"]}/rlbot/{name}'
        try:
            subprocess.run(["curl", "-fLsS", "--retry", "2", "--max-time", "120", url, "-o", str(temporary)], check=True)
            if digest(temporary) != expected:
                raise ValueError("Chronos download checksum mismatch: " + name)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return verify_assets(folder)


class Chronos(nn.Module):
    def __init__(self, folder):
        super().__init__()
        folder = verify_assets(folder)
        self.shared = self._sequence(folder / "SHARED_HEAD.lt", [225, 960, 960], False)
        self.policy = self._sequence(folder / "POLICY.lt", [960, 960, 800, 640, 640, 90], True)
        self.eval()

    @staticmethod
    def _sequence(path, widths, output):
        modules = []
        for i, (a, b) in enumerate(zip(widths, widths[1:])):
            modules.append(nn.Linear(a, b))
            if not output or i < len(widths) - 2:
                modules.extend([nn.LayerNorm(b, eps=1e-5), nn.ReLU()])
        net = nn.Sequential(*modules)
        state = torch.jit.load(str(path), map_location="cpu").state_dict()
        if {k: tuple(v.shape) for k, v in state.items()} != {k: tuple(v.shape) for k, v in net.state_dict().items()}:
            raise ValueError("Unexpected Chronos architecture")
        if not all(torch.isfinite(v).all() for v in state.values()):
            raise ValueError("Non-finite Chronos parameter")
        net.load_state_dict(state, strict=True)
        return net

    def forward(self, obs):
        return self.policy(self.shared(obs))


def action_mask(ground, boost, flip, turtled=False):
    mask = []
    for i, a in enumerate(ACTIONS):
        # Preserve the exact upstream ordering, including jump-mask union last.
        enabled = i < 24 if ground else (i > 24 and not a[5]) or (
            i < 24 and a[0] == a[6] and bool(a[3]) == bool(a[7]))
        if boost == 0 and a[6]:
            enabled = False
        if (flip or turtled) and a[5]:
            enabled = True
        mask.append(bool(enabled))
    if not any(mask):
        raise ValueError("Empty Chronos action mask")
    return mask


def resolve_action(index, mirror):
    a = ACTIONS[index].copy()
    if mirror:
        a[[1, 3, 4]] *= -1
    return a


def _vec(body, name):
    result = np.asarray(body[name], dtype=np.float64)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError("Invalid Chronos vector: " + name)
    return result


def _physics(body, inv, mirror):
    polar = np.array([-1 if inv else 1, -1 if inv else 1, 1.])
    axial = polar.copy()
    if mirror:
        polar[0] *= -1
        axial *= [1, -1, -1]
    return {"position": _vec(body, "position") * polar,
            "velocity": _vec(body, "velocity") * polar,
            "angular_velocity": _vec(body, "angular_velocity") * axial,
            **({"forward": _vec(body, "forward") * polar, "up": _vec(body, "up") * polar} if "forward" in body else {})}


def pad_values(packet):
    values = np.zeros(34, dtype=np.float64)
    assigned = set()
    for pad in packet.get("boost_pads", []):
        pos = np.asarray(pad["position"][:2])
        distance = np.linalg.norm(PADS[:, :2] - pos, axis=1)
        distance[(PADS[:, 2] > 72) != pad["is_big"]] = np.inf
        i = int(distance.argmin())
        if distance[i] > 256 or i in assigned:
            continue
        assigned.add(i)
        if pad["active"]:
            values[i] = 1
        else:
            timer = pad.get("cooldown_remaining")
            timer = (10 if pad["is_big"] else 4) if timer is None else timer
            values[i] = 1 / (1 + np.clip(timer, .01, 10 if pad["is_big"] else 4))
    return values


def observe(packet, previous, has_flip, rng=None):
    inv = packet["team"] == 1
    mirror = packet["car"]["position"][0] * (-1 if inv else 1) > 0
    ball = _physics(packet["ball"], inv, mirror)
    obs = [*(ball["position"] / 5000), *(ball["velocity"] / 2300), *(ball["angular_velocity"] / 3)]
    prev = np.asarray(previous).copy()
    if prev.shape != (8,) or not np.isfinite(prev).all():
        raise ValueError("Invalid previous Chronos action")
    if mirror:
        prev[[1, 3, 4]] *= -1
    obs.extend(prev)
    pads = pad_values(packet)
    if inv:
        pads = pads[::-1]
    if mirror:
        pads = pads[MIRROR_PADS]
    obs.extend(pads)

    def row(body, boost, ground, flip, jumped, demoed=False):
        p = _physics(body, inv, mirror)
        f, u = p["forward"], p["up"]
        axes = np.array([f, np.cross(u, f), u])
        return [*(p["position"] / 5000), *f, *u, *(p["velocity"] / 2300),
                *(p["angular_velocity"] / 3), *(axes @ p["angular_velocity"] / 3),
                *(axes @ (ball["position"] - p["position"]) / 5000),
                *(axes @ (ball["velocity"] - p["velocity"]) / 2300),
                boost / 100, float(ground), float(flip), float(demoed), float(jumped)]

    ground = packet["ground_estimate"]
    obs.extend(row(packet["car"], packet["boost"], ground, has_flip, packet.get("has_jumped", not ground), packet.get("is_demoed", False)))
    teams = [[], []]
    for other in packet.get("other_cars", []):
        g = other["ground_estimate"]
        teams[int(other["team"] != packet["team"])].append(row(other, other.get("boost_estimate", 50), g,
            other.get("flip_estimate", g), other.get("has_jumped", not g), other.get("is_demoed", False)))
    for players, count in zip(teams, [2, 3]):
        if len(players) > count:
            raise ValueError("Chronos supports at most three cars per team")
        players.extend([[0.] * 29 for _ in range(count - len(players))])
        if rng is not None:
            rng.shuffle(players)
        for player in players:
            obs.extend(player)
    out = np.asarray(obs, dtype=np.float32)
    if out.shape != (225,) or not np.isfinite(out).all():
        raise ValueError("Invalid Chronos observations")
    context = {"mirror": bool(mirror), "entity_count": 2 + len(packet.get("other_cars", [])),
               "mask": action_mask(ground, packet["boost"], has_flip, packet.get("turtled", False))}
    return out, context


def fixtures():
    """Physical states covering both teams, reflection, contact, air and pad timers."""
    cases = []
    for team in (0, 1):
        for x in (-1200, 1200):
            for ground in (True, False):
                p = {"team": team, "boost": 0 if ground else 63, "ground_estimate": ground,
                    "has_jumped": not ground,
                    "car": {"position": [x, -2200, 17 if ground else 620], "velocity": [350, 900, 0 if ground else 280],
                        "forward": [.6, .8, 0], "up": [0, 0, 1], "angular_velocity": [.2, -.4, .7]},
                    "ball": {"position": [200, -850, 140], "velocity": [-240, 700, 180], "angular_velocity": [1.1, -.2, 2.3]},
                    "other_cars": [],
                    "boost_pads": [{"position": v.tolist(), "active": i % 3 != 0, "is_big": bool(v[2] > 72),
                                    "cooldown_remaining": .8 + i % 3} for i, v in enumerate(PADS)]}
                other = dict(p["car"], position=[-x, 1500, 17], team=1-team,
                             boost_estimate=47, ground_estimate=True, flip_estimate=True, has_jumped=False)
                p["other_cars"] = [other]
                cases.append((p, ACTIONS[32].tolist(), ground or x < 0))
    return cases


def prepare_model(model):
    tensors = {k: v.detach().cpu().numpy().astype("<f4") for k, v in model.state_dict().items()}
    cases = []
    with torch.inference_mode():
        for packet, previous, flip in fixtures():
            obs, context = observe(packet, previous, flip)
            logits = model(torch.from_numpy(obs).unsqueeze(0))[0]
            masked = logits.masked_fill(~torch.tensor(context["mask"]), -float("inf"))
            cases.append({"query": obs.tolist(), "entities": context,
                          "logits": logits.tolist(), "action": int(masked.argmax()) + 1})
    return tensors, cases
