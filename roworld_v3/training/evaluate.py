"""Paired held-out seeds against the built-in policy. Truncated episodes are not wins."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from bridge import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", type=Path, required=True)
    p.add_argument("--luau", type=Path, required=True)
    p.add_argument("--weights", type=Path)
    p.add_argument("--games", type=int, default=8)
    p.add_argument("--seed", type=int, default=900001)
    p.add_argument("--seconds", type=int, default=540)
    p.add_argument("--stage", type=int, choices=range(4), default=1)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--out", type=Path, default=Path("evaluation.json"))
    args = p.parse_args()
    if min(args.games,args.seconds,args.workers)<1:
        p.error("Counts must be positive")
    weights = json.loads(args.weights.read_text()) if args.weights else None
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for version, model in (("built_in", None),("trained", weights)) if weights else (("built_in", None),):
            futures = [pool.submit(run, args.luau.resolve(), args.engine.resolve(), model,
                                   args.seed+i, args.seconds, args.stage, False) for i in range(args.games)]
            for f in futures:
                episode = f.result();episode.pop("rows",None);episode["version_name"]=version;rows.append(episode)
                print(json.dumps(episode), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"scope": "Paired synthetic original-RoWorld-engine seeds; not human competitive strength", "games": rows,
                                    "competitive_strength_verified": False}, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
