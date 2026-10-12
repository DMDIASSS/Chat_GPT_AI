# Slater v0.3.8 — RLBot vs RocketSim fidelity gate (read-only)

**Purpose:** identify observation-semantic discrepancies and Nexto scripted-kickoff mismatches **before** another PPO campaign. This release deliberately does **not** train, edit or export models. The `v037a` two-update `u62` experiment was not demonstrably stronger; it must not replace u60 or OG Champion.

## Contents

- `slater_fidelity_v038.py`: reuses **the exact archived v4 NextoObsBuilder logic** by extracting vetted AST declarations from `slater_v038_reference/nexto_obs.py` (SHA-256 pinned). Converts each RLGym v2 RocketSim state to the documented legacy Nexto flat representation, then calls the original builder and compares its q/KV/mask with `afk_team_research.TeamObserver` on the **identical state**. Optional V60 TorchScript model evaluates whether discrepancies change the selected action.
- `slater_kickoff_audit_v038.py`: compares known v037a source behavior against official archived Nexto kickoff policy; reports specific mismatches. This is a **source audit**, not a live validation of RLBot physics.
- `slater_v038_reference/nexto_obs.py` and `nexto_bot.py`: original Nexto files taken unmodified from the **RLBotPack-master.zip that you uploaded**; kept in a reference-only folder and never imported as RLBot agents.
- `slater_v038_tests/`: offline unit tests.

## Windows installation

Extract ZIP into `E:\Downloads\Chat_GPT_AI`, with paths preserved; the included `slater_v038_reference` folder needs to remain in the project root. Do **not** extract over `data\rlbot_exports\V60`, `vendor\nexto`, or any checkpoint.

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v038_tests -q
```

The two scripts only **write new JSON files** underneath `data\isolated`; the output filenames are create-only. If they exist, choose `02.json`, `03.json`, etc.

### A. Audit Nexto reference and deployed observation-builder provenance

```bat
.venv\Scripts\python.exe slater_fidelity_v038.py audit --out data/isolated/v038_reference_audit01.json
```

`deployed_obs.same_as_reference` should be `true` if your copied V60 folder uses exactly the archived Nexto observation builder. If false, do not claim real RLBot parity; report the hashes.

### B. Source-grounded scripted kickoff audit

```bat
.venv\Scripts\python.exe slater_kickoff_audit_v038.py --out data/isolated/v038_kickoff_audit01.json
```

The script identifies known differences between reference RLBot Nexto and v037a simulator: kickoff pause, clock, taker selection, scripted interruption, and stochastic period. These are genuine source-level differences; their magnitude in match outcomes still needs measurement.

### C. The important one: same-state observation check

```bat
.venv\Scripts\python.exe slater_fidelity_v038.py compare-obs --seeds 2 --steps 4 --model data/rlbot_exports/V60/nexto-model.pt --out data/isolated/v038_same_state_obs01.json
```

Uses 2 different kickoff RNG seeds, both Blue and Orange, plus four eight-tick transitions for each: expected **20 observation comparisons** total. Each compares q `(1,32)`, KV `(41,24)`, and mask `(41,)`, with per-feature and per-token mismatches. The optional model comparison provides `sim_action`, `reference_action`, `same_selected_action`, and logit discrepancies. All observations use the **same RocketSim state**, not unrelated live and simulated gameplay. The legacy encoded-state adapter uses normalized boost `boost_amount / 100` and legacy `has_flip` (not `can_flip`) and converts boost cooldown to availability; these assumptions must be inspected if discrepancies appear.

If the reference builder reports mismatches, **do not silently patch TeamObserver**, and do not promote any checkpoint. Share the JSON so the actual field causes can be assessed. Even if *all* samples pass, equivalence to RLBot game packets, physics and scheduling remains **unverified**.

### D. Optional existing live capture sanity check

If you have v034 live capture snapshots already:

```bat
.venv\Scripts\python.exe slater_fidelity_v038.py inspect-capture --out data/isolated/v038_live_capture_audit01.json
```

This only checks that captured vectors are usable. It does not compare equivalent physical states, so it **cannot prove live observation parity**. If the v034 `capture_v034` folder does not exist, skip this command.

## Known, independently grounded findings

The uploaded RLBotPack Nexto has `hardcoded_kickoffs=True` and `stochastic_kickoffs=True` in its `Nexto.__init__` defaults. Actual runtime configuration of a different installed Nexto bot has not been verified.

The reference kickoff sequence lasts 168 physics ticks; the RLBot code advances its index from packet elapsed time and applies script only to the selected kickoff taker while `is_kickoff_pause` is true and the ball's `y == 0`. v037a approximates this via `t*8`, centered ball and untouch logic. Stochastic sampling in RLBot uses the `is_kickoff_pause` flag rather than just the v037a `active` predicate.

**Pre-existing results:** u60 31/32 full RocketSim games against greedy Nexto (v0304a, 16 seeds, two sides). u60 6/8 wins in 600-step greedy single-goal episodes but 4/8 vs scripted; u62 two PPO updates did not demonstrate improvement. None of these are controlled full RLBot win rates.

## Model and environment safety

- No GitHub downloads, network calls or training in these scripts.
- No modification or overwrite of source files, models, model exports, or existing reports.
- Strict Nexto reference `nexto_obs.py` SHA256 prevents silently treating a different builder as the same one.
- `inspect-capture` does not execute bot code or deserialize unsafe pickle; NPZ loads with `allow_pickle=False`.
- `compare-obs` requires the project's installed `rlgym`, `afk_team_research`, NumPy; optional model inference additionally requires PyTorch. These dependencies are already used by prior Slater scripts; no new packages are specified by this bundle.
- Unit tests can run in an environment without RocketSim to check most static functionality. **Real physics integration has not been run in this Linux sandbox**, so report any Windows import/schema errors.

## Send back

`v038_reference_audit01.json`, `v038_kickoff_audit01.json`, and especially `v038_same_state_obs01.json`. If the third script fails, send its exact traceback. Do not start another large PPO campaign until observations and opponent semantics are understood.
