# Read-only fidelity audit (v0.1.3)

## Current status
- On Windows, v0.1.2 successfully exported **71 candidate clips from the first 10 replay files** (15 local regression tests passed).
- Export success **does not** guarantee the replay-derived actions reproduce an actual goal when RocketSim simulates counterfactual interactions.

This patch adds a standalone audit entry point. **It never starts PPO, loads Cycle 9 weights, or changes checkpoints.** It loads `.npz` clips, calls the existing research `counterfactual_goal_check`, and writes a new JSON report with per-scenario fidelity results.

## Install
Unzip the patch into `E:\Downloads\Chat_GPT_AI` (merge the `slater_research` folder).

## Run (Windows CMD)
```
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.fidelity_audit --clips data\replay_scenarios_smoke_v012 --limit 5 --out data\replay_scenarios_smoke_v012\fidelity_sample5.json
```

The fidelity audit does not delete or rewrite any `.npz` clip. It refuses to overwrite its JSON report. If the report path already exists, supply a new output name. The simulation uses *inferred* replay controls plus teleported ghost-car snapshots. Inspect any accepted shots visually and test them with adaptive opponents before believing the replay scenario is sufficiently faithful.

Send back the `SUMMARY` line and per-clip `accepted`, `scored`, `ball_error_uu`, `error` lines. Stop if none pass; do NOT launch training.
