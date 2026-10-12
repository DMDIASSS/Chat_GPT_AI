# Slater v0.3.9 — Large-scale training throughput preflight

## Decision

We can aim for 10M, 100M, 1B+ action decisions using RocketSim, but do not start a billion-decision run with unmeasured single-process collection. This package measures your actual CPU + Torch + RocketSim speed. It **does not train**.

## Proven groundwork

- v038a 8-tick vs single-tick physics state equivalence for one test trajectory: max error 0.0.
- v038a same-simulator Nexto observation parity: 528/528, with zero neural action disagreements.
- v038c real RLBot stock-Nexto controller scheduling audit: 3,584 packets, 453 neural update times matched, zero reported final controls mismatches; this uses logged neural actions and does NOT prove live observation or RocketSim physics parity.
- v038b tick-aware simulator: more faithful controller timing but uses kickoff pause proxy and up to 8 engine.step calls per agent decision.
- V60 is reported by user to hold real Nexto under pressure and outscore it, but full match count and goal-difference statistics not yet collected. Don't demote or edit it.

## Install

Extract only the Python script and tests to `E:\Downloads\Chat_GPT_AI` (project root). Requires the prior v037a and v038b packages and existing protected V60, Cycle9, Nexto weights already installed on your PC. No new dependencies.

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v039_tests -q
```

Expected `12 passed`.

## Read-only measurement

Run a quick preflight. The command compares a fast **eight-tick batch** script opponent to a **per-physics-tick** approximation of stock Nexto; it does NOT compare win rates:

```bat
.venv\Scripts\python.exe slater_v039_throughput.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --modes old_script,tick_stock --decisions 256 --warmup 16 --max-episode-steps 600 --seed 20261011 --out data/isolated/v039_rollout_speed01.json
```

Repeat with a longer duration to reduce stopwatch noise, using a **new filename**:

```bat
.venv\Scripts\python.exe slater_v039_throughput.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --modes old_script,tick_stock --decisions 1024 --warmup 32 --max-episode-steps 600 --seed 20261011 --out data/isolated/v039_rollout_speed02.json
```

Both run a single environment in one Python process, including V60 forward passes and opponent forward passes, without gradient updates. These are **upper bounds for effective single-process PPO throughput**, since optimizer updates, validation, checkpointing, and any other bookkeeping are excluded. More simulation processes can increase aggregate throughput, but scale efficiency must be tested separately.

## What the report means

`decisions_per_second`: completed student action selections per real-world second.
`nominal_physics_ticks_per_second`: decisions per second multiplied by eight (for accounting; tick-aware engine may end on an intermediate tick at a goal).
`equivalent_single_agent_realtime_multiplier`: gameplay-speed equivalent, computed as decisions/s divided by 15.
`wallclock_hours_at_measured_rollout_rate`: illustrative *collection-only* time, not a training runtime promise.

At action repeat 8 and physics 120Hz, one million decisions are 18.52 simulated agent-hours. One billion is ~18,519 agent-hours. A billion decisions at 10,000 effective decisions/s would require ~27.8 wall-clock hours for rollout only. Your actual rate may be far smaller, especially with per-tick RocketSim state inspection and transformer inference in Python.

## Next practical development work — not completed in this preflight

1. Establish a real RLBot score baseline for V60, OG Champion, Cycle9 on both team sides vs stock Nexto, including score lines, kickoff goals and own goals; even 5-10 full matches/bot is a useful initial sample.
2. After measuring speed, replace serial rollout with subprocess-based parallel episode collection or a faster native runner; avoid GPU rollout contention and guard TorchScript loading, RNG and seed pairing. Integrate verified stock-Nexto kickoff scheduling rather than assuming the old controller is equivalent.
3. Use the strongest current V60 as a protected teacher and start a new isolated training campaign, first 1M-10M collected decisions, then scale only after held-out and live improvements. Include greedy, stock-approximate, Cycle9, earlier Slater versions, defense/counterattacks, and a small set of state-conditioned recovery scenarios.
4. Evaluate checkpoints by paired long-form simulated matches *and* live full matches; preserve V60's unusual aggressive play if it improves goals per match. Never promote a new version based on reward curves alone.
5. Separately validate TAS controller mapping and replay-to-RocketSim inverse dynamics before using them as ground truth imitation actions; the 108,461 extracted TAS frames are not state-to-action trajectories yet.

## Important restrictions

- No checkpoint writes.
- No automatic model promotion.
- Out filenames are create-only under `data/isolated`.
- A speed benchmark cannot guarantee equal speed in self-play, GPU training, or full matches.
- `torch.jit.load` deprecation warnings do not invalidate this test, but the ecosystem may eventually need migration.
