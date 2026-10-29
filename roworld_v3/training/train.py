"""Train a compact RoWorld residual policy with PPO on the user's original simulator.

Example: python training/train.py --engine private/engine.json --luau tools/luau.exe --updates 50 --workers 3
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
import torch
from torch.distributions import Categorical
from bridge import ROOT, build, engine_source, run
from model import Model, batch, SCHEMA


def advantages(episode, gamma=.997, lam=.95):
    rows = episode["rows"]
    gae, next_value = 0.0, episode["bootstrap"]
    for row in reversed(rows):
        alive = 0.0 if row["done"] else 1.0
        delta = row["reward"] + gamma*next_value*alive - row["value"]
        gae = delta + gamma*lam*alive*gae
        row["advantage"] = gae
        row["return"] = gae + row["value"]
        next_value = row["value"]
    return rows


def optimize(model, optimizer, rows, device, epochs=4, batch_size=128):
    if not rows:
        raise ValueError("No decisions returned by simulator")
    raw_adv = torch.tensor([r["advantage"] for r in rows])
    raw_adv = (raw_adv-raw_adv.mean()) / raw_adv.std(unbiased=False).clamp_min(1e-6)
    for r, value in zip(rows, raw_adv.tolist()):
        r["normalized_advantage"] = value
    stats = []
    for _ in range(epochs):
        for indices in torch.randperm(len(rows)).split(batch_size):
            subset = [rows[i] for i in indices.tolist()]
            logits, value = model(*batch(subset, device))
            distribution = Categorical(logits=logits)
            choices = torch.tensor([r["choice"]-1 for r in subset], device=device)
            old_logp = torch.tensor([r["logp"] for r in subset], device=device)
            adv = torch.tensor([r["normalized_advantage"] for r in subset], device=device)
            returns = torch.tensor([r["return"] for r in subset], device=device)
            log_ratio = distribution.log_prob(choices)-old_logp
            ratios = log_ratio.exp()
            policy_loss = -torch.minimum(ratios*adv, ratios.clamp(.8, 1.2)*adv).mean()
            value_loss = (value-returns).square().mean()
            entropy = distribution.entropy().mean()
            loss = policy_loss + .5*value_loss - .01*entropy
            if not torch.isfinite(loss):
                raise ValueError("Non-finite PPO loss; checkpoint not overwritten")
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), .5)
            optimizer.step()
            stats.append({"loss": loss.item(), "policy_loss": policy_loss.item(), "value_loss": value_loss.item(), "entropy": entropy.item()})
    return {key: sum(s[key] for s in stats)/len(stats) for key in stats[0]}


def atomic_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf8")
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", type=Path, required=True)
    p.add_argument("--luau", type=Path, required=True)
    p.add_argument("--out", type=Path, default=ROOT/"runs/first")
    p.add_argument("--updates", type=int, default=50, help="Additional updates; resumes latest.pt in this run")
    p.add_argument("--episodes", type=int, default=6, help="Episodes per update")
    p.add_argument("--seconds", type=int, default=180, help="Game seconds per episode; timeouts bootstrap rather than count as wins")
    p.add_argument("--workers", type=int, default=min(3, max(1, (os.cpu_count() or 2)-1)))
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--seed", type=int, default=1729)
    p.add_argument("--stage", type=int, choices=range(4), default=1)
    p.add_argument("--init", type=Path, help="Start a new run/curriculum stage from a previous stage's latest.json")
    args = p.parse_args()
    if min(args.updates,args.episodes,args.seconds,args.workers,args.threads) < 1:
        p.error("Counts must be positive")
    if not args.luau.is_file():
        p.error("Provide the official Luau CLI executable path; this is separate from JJSploit")
    _, engine_hash = engine_source(args.engine)
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    if device == "cuda" and not torch.cuda.is_available():
        p.error("CUDA PyTorch is unavailable; install it using pytorch.org or use --device cpu")
    args.out.mkdir(parents=True, exist_ok=True)
    contract = {"schema": SCHEMA, "engine_sha256": engine_hash,
                "agent_sha256": hashlib.sha256(build.modules_source().encode()).hexdigest(),
                "worker_sha256": hashlib.sha256((ROOT/"training/worker.lua").read_bytes()).hexdigest(),
                "stage": args.stage, "seconds": args.seconds, "seed": args.seed, "episodes": args.episodes}
    model = Model().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    start, steps = 0, 0
    checkpoint = args.out/"latest.pt"
    if checkpoint.exists():
        saved = torch.load(checkpoint, map_location=device, weights_only=True)
        if saved["contract"] != contract:
            p.error("Run observation/engine/curriculum changed. Existing files preserved; select a new --out folder.")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["torch_rng"].cpu())
        start, steps = saved["update"], saved["steps"]
    elif args.init:
        model.load_json(args.init)
    manifest = {"version": 1, "parameters": sum(t.numel() for t in model.parameters()), "contract": contract,
                "reference": "https://github.com/djmango/openfront-ai/tree/474536340480659c53d9a9e497b08fa1fefb9589",
                "device": device, "workers": args.workers,
                "environment": "Original supplied RoWorld simulator, synthetic curriculum maps",
                "competitive_strength_verified": False}
    atomic_json(args.out/"manifest.json", manifest)
    print(f"{manifest['parameters']} parameters | device={device} | workers={args.workers} | resume update={start}", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for update in range(start+1, start+args.updates+1):
                began = time.monotonic()
                weights = model.export()
                futures = [pool.submit(run, args.luau.resolve(), args.engine.resolve(), weights,
                                       args.seed+update*args.episodes+i, args.seconds, args.stage, True,
                                       weights if args.stage>=3 and i%2 else None) for i in range(args.episodes)]
                episodes = [f.result() for f in futures]
                rows = [row for e in episodes for row in advantages(e)]
                stats = optimize(model, optimizer, rows, device)
                steps += len(rows)
                summary = {"update": update, "steps": steps, "seconds_elapsed": time.monotonic()-began,
                           "mean_land": sum(e["land"] for e in episodes)/len(episodes),
                           "deaths": sum(not e["alive"] for e in episodes),
                           "terminal_wins": sum(e["win"] for e in episodes),
                           "truncations": sum(e["truncated"] for e in episodes), **stats}
                temp = checkpoint.with_suffix(".tmp")
                torch.save({"contract": contract, "model": model.state_dict(), "optimizer": optimizer.state_dict(),
                            "torch_rng": torch.get_rng_state(), "update": update, "steps": steps}, temp)
                temp.replace(checkpoint)
                model.save_json(args.out/"latest.json")
                if update%10==0:
                    model.save_json(args.out/f"update_{update:05d}.json")
                with (args.out/"progress.jsonl").open("a", encoding="utf8") as f:
                    f.write(json.dumps(summary, allow_nan=False)+"\n")
                print(json.dumps(summary), flush=True)
    except KeyboardInterrupt:
        print("Stopped. Latest completed update is saved; run the same command to resume.")
    print(f"Export: python build.py --weights {args.out/'latest.json'} --output RoWorld_V3_Trained.lua")
    print("Evaluate held-out seeds before replacing a working bot; training loss is not multiplayer strength.")


if __name__ == "__main__":
    main()
