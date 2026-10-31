"""Build the independent v3 standalone; optionally embed your own trained JSON weights."""
import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = (("Weapons", "shared/weapons.lua"), ("Coalition", "shared/coalition.lua"), ("Cooperation", "shared/cooperation.lua"),
           ("Profiles", "shared/profiles.lua"), ("Recorder", "shared/recorder.lua"),
           ("Adapter", "shared/adapter.lua"), ("Wire", "shared/wire.lua"),
           ("Mirror", "shared/mirror.lua"), ("Network", "shared/network.lua"),
           ("Schema", "schema.lua"), ("Geography", "geography.lua"), ("Observe", "observe.lua"),
           ("Actions", "actions.lua"), ("Neural", "neural.lua"), ("Agent", "agent.lua"))


def validate_weights(weights):
    if not isinstance(weights, dict) or weights.get("schema") != "roworld-observation-v1" or weights.get("version") != 1:
        raise ValueError("Only RoWorld v3 model JSON is compatible; OpenFront weights cannot be used")
    for name, (rows, cols) in {"context": (32, 204), "action": (32, 48), "fusion": (32, 32), "score": (1, 32), "value": (1, 32)}.items():
        layer = weights.get(name, {})
        w, b = layer.get("w", []), layer.get("b", [])
        if len(w) != rows or len(b) != rows or any(not isinstance(row, list) or len(row) != cols for row in w):
            raise ValueError("Invalid model layer shape: " + name)
        for v in b + [x for row in w for x in row]:
            if type(v) not in (int, float) or not math.isfinite(v) or abs(v) >= 1e6:
                raise ValueError("Invalid model value: " + name)


def literal(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Non-finite model value")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, list):
        return "{" + ",".join(literal(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ",".join("[" + literal(k) + "]=" + literal(v) for k, v in value.items()) + "}"
    raise TypeError(type(value))


def modules_source():
    parts = []
    for name, path in MODULES:
        code = (ROOT / path).read_text(encoding="utf8")
        code = re.sub(r"local (\w+)\s*=\s*require\(['\"]\./[^'\"]+['\"]\)", "", code)
        parts.append(f"local {name}=(function()\n{code}\nend)()\n")
    return "\n".join(parts)


def source(weights=None):
    header = "-- RoWorld 3.1.0 | independent observation / candidate policy\n"
    header += "-- No OpenFront weights; no external runtime downloads.\n"
    return header + modules_source() + "\nlocal ModelWeights=" + literal(weights) + "\nlocal Policy=Agent\n" + (ROOT / "client.lua").read_text(encoding="utf8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weights", type=Path)
    p.add_argument("--output", type=Path, default=ROOT / "RoWorld_V3.lua")
    args = p.parse_args()
    try:
        weights = json.loads(args.weights.read_text(encoding="utf8")) if args.weights else None
        if args.weights:
            validate_weights(weights)
    except (ValueError, TypeError, AttributeError, OSError) as e:
        p.error(str(e))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source(weights), encoding="utf8", newline="\n")
    print(args.output)


if __name__ == "__main__":
    main()
