# Slater Research v0.2.0 — controlled defender car-state repair

**Status:** experimental, isolated, offline-capable, not a PPO trainer. All commands use the existing installed dependencies and do not write to replay, original NPZ, Cycle 9, or checkpoints.

## Why

RLGym Tools 2.6.5 `replay_to_rlgym(..., interpolation='linear')` carries certain car/jump flags between replay frames even though the actual jump/ground state is not fully observed. In the uploaded 1v1 clips, many cars have `is_jumping=True` and `jump_time=0`, including frames with no inferred jump input. RocketSim engine correctly applies these serialized flags in `set_state`. A replay-derived goal reproducing correctly does not validate the car state for defensive counterfactual training.

## What v0.2.0 changes

- Selects **train split** and proximity-prioritized clips from the existing v0.1.6 scenario catalog. Independently checks the replay SHA and train split.
- Treats demos as **not trainable** at the selected start; no changes to a demolished defender.
- In default `jump_only` mode, clears a defender's stale `is_holding_jump` and `is_jumping` flags only when **previous, current and next recorded inferred jump controls are all zero** (where present). Changes only the selected end-of-clip window.
- **Does not infer new ground contact in the default mode**. An opt-in `ground_heuristic` mode is available for explicitly experimental comparison, requiring flat-floor, upright, steady, interior-field positions; do not use it first.
- Preserves **ball pose/velocity, both cars' physics poses/velocities, attacker car state, actions, replay SHA, shot metadata** unchanged. New NPZs remain derivations requiring physics revalidation.
- Produces derived NPZs only under a **new separate directory**, and writes hashes + change counters to a JSON provenance report. Existing outputs cannot be overwritten.
- `car_state_compare` checks that both the original and repaired dual-mode RocketSim goals still match the reference under the **same selected start step and window**.

## Install

Extract the ZIP into `E:\Downloads\Chat_GPT_AI`, merging only new files under `slater_research`. The patch includes no replacements for the original trainer, clips or policy.

## Run with the first 12 candidate clips

In Windows CMD, run each command on one line:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.car_state_repair --clips data\replay_scenarios_smoke_v012 --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --limit 12 --out-dir data\replay_scenarios_carfix_v020_12 --report data\replay_scenarios_smoke_v012\car_state_repair_v020_12.json
.venv\Scripts\python.exe -m slater_research.goal_tail_audit --clips data\replay_scenarios_carfix_v020_12 --limit 12 --windows 0.5,1 --post-seconds 0.3 --out data\replay_scenarios_carfix_v020_12\goal_tail_repaired_v020_12.json
.venv\Scripts\python.exe -m slater_research.car_state_compare --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --repair-report data\replay_scenarios_smoke_v012\car_state_repair_v020_12.json --original-audit data\replay_scenarios_smoke_v012\goal_tail_full_v015.json --derived-audit data\replay_scenarios_carfix_v020_12\goal_tail_repaired_v020_12.json --out data\replay_scenarios_carfix_v020_12\comparison_v020_12.json
```

Expected local unit test result: **74 passed**, using the full previously merged v0.1.9 tree plus the two new tests. Real RocketSim post-repair results are unknown until you run them. Do **not** compare to all 71 original windows by aggregate totals; compare only the selected window, which the comparator does automatically.

If an output directory/file exists, choose a **new** suffix (`_retry`) rather than overwriting. Send the CMD `SUMMARY` output and `comparison_v020_12.json` when complete.

## Important interpretation

- A failed corrected replay goal means the change disrupted replay-physics fidelity. **Exclude** it; do not train from it.
- A passed corrected replay goal is **still not a saveability test**. Follow with controlled movement and actual touch tests, then train with isolated checkpoints only after both positive controls and held-out evaluation are validated.
- Do not repair validation/test split clips during this research stage. Keep all holdout sets and Cycle 9 checkpoint unchanged.
