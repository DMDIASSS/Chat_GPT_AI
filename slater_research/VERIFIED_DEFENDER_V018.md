# Slater Research v0.1.8 — Verified Defender Environment (offline-prepared)

## What's new

- `verified_defender_env.py`: isolated all-dynamic 1v1 **defender** scenario, from **v0.1.6 verified catalog windows**. No opponent teleports, no long unverified starts. Reference attacker controls are unchanged, while an external policy can override the defender.
- The scenario ends at an actual scored goal or at **goal_step + verified tail_steps**, not at the last saved replay frame.
- Goal conceded: -5; defender scores: +5; first defender contact: +0.1. `no_goal_by_deadline` receives **no positive terminal reward** and is explicitly **NOT** counted as a successful save. These are initial research reward parameters, not tuned hyperparameters.
- `verified_defender_preflight.py`: **read-only** integration parity test; independently reproduces the same original scoring shot using the v0.1.7 positive-control simulator and the v0.1.8 environment. Only training-split catalog scenarios are selected.
- Four environment tests and three preflight tests, in addition to the existing 47 tests.

## Compatibility and prerequisites

Install **all prior incremental patches up to v0.1.7**, including `shot_catalog_v016.json` and `.npz` clips. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`, merging `slater_research/` without deleting earlier modules. This ZIP contains **only the new files**.

No Internet is needed to run these commands if Python, NumPy, pytest and RocketSim are already installed in your `.venv`. There is no network request in the new code.

### Windows CMD, later when convenient

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.verified_defender_preflight --clips data\replay_scenarios_smoke_v012 --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --limit 12 --out data\replay_scenarios_smoke_v012\defender_preflight_v018_12.json
```

Expected unit tests: **54 passed** when all previous patches are correctly installed. The preflight command prints real RocketSim results and writes the JSON report with statuses `consistent`, `not_reproduced_or_mismatch`, or `error`. If an output path already exists, choose another filename; the tool refuses overwrites.

The v0.1.7 counterfactual audit should still be run separately when convenient:

```bat
.venv\Scripts\python.exe -m slater_research.counterfactual_audit --clips data\replay_scenarios_smoke_v012 --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --limit 12 --split train --out data\replay_scenarios_smoke_v012\counterfactual_v017_12.json
```

## Safety and limitations

1. **Do not run the old `train_scenarios.py` defender phase yet.** It doesn't implement the approved tail-aware training setup.
2. **Do not interpret no-goal-by-deadline as a physical save.** The shot might be delayed rather than intercepted.
3. v0.1.8 is **not a PPO trainer**, and intentionally does not load the Cycle 9 actor, modify any checkpoint or promote the champion.
4. **RocketSim real integration was not available in the model's local environment**. All **54 offline unit tests passed**, including fake deterministic physics tests and structural inspection of the user's uploaded `.npz` clips. The PC preflight is still required before training.
5. Replay controls are inferred, not exact ground-truth player inputs. Only train-split 1v1 scenarios are supported; 2v2/3v3 and held-out evaluations require separate validation.

## Next milestone

After the counterfactual report and parity preflight show reproducible outcomes, integrate the 90-action Nexto attention policy and PPO **in a separate candidate output**, with a frozen Cycle 9 teacher, a verified positive-control baseline, replay-level holdout evaluation, and no checkpoint promotion until demonstrated improvement.
