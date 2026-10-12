# Slater Research v0.1.7 — Counterfactual Defender Audit (read-only)

## Purpose

Check whether simple changes to DEFENDER controls can alter the outcome of a verified short-window replay goal. This is a *diagnostic*, not PPO training, proof of physical reachability, or a measured save rate. All-dynamic RocketSim is used (not ghosted teleporting attackers).

Prerequisites: the original research add-on and incremental hotfixes through v0.1.6, with `shot_catalog_v016.json` and the 71 `.npz` clips in the original directory. This ZIP is incremental, and it contains only one new module and its six tests plus this document. **Don't remove the installed `slater_research` directory.**

## Windows CMD

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.counterfactual_audit --clips data\replay_scenarios_smoke_v012 --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --limit 12 --split train --out data\replay_scenarios_smoke_v012\counterfactual_v017_12.json
```

Expected local tests: 47 passed when all earlier components are installed. **Actual Windows/RocketSim outcomes are unknown until run.**

## What it does

1. Selects up to 12 train-split verified clips, cycling through source-replay groups first and prioritizing close defenders.
2. Validates the NPZ SHA, stored goal step, roster and defender team.
3. Creates fresh RocketSim engine for each probe, with the same starting snapshot and the same inferred ATTACKER controls.
4. Checks the original defender replay controls in all-dynamic physics as an independent positive control: attacker scores at the annotated endpoint or within the approved tail window; ball tracking remains <=250 uu.
5. Only when positive control passes, substitutes each defender's controls with simple test probes:
   - `neutral` (zero inputs),
   - `brake` (throttle=-1),
   - `boost_straight` (throttle=1, boost=1),
   - `jump_boost` (throttle=1, boost=1, jump pulse first decision).
6. Reports the goal outcome under each intervention at the **same fixed time horizon**, plus ball deviation at the reference endpoint. All observations are **limited to the short verified window** and 0.27-second goal tail.

An intervention that merely delays a goal past the deadline can be counted as an outcome change; the tool therefore uses `goal_outcome_changed_by_deadline` and NEVER calls it a confirmed save. It is not a substitute for trainable, reactive defender policies. Evaluation splits are not used by default.

## Output

`counterfactual_v017_12.json`, with per-clip statuses `counterfactuals_evaluated`, `baseline_not_reproduced`, or `error`. The `SUMMARY` shows total selected, reproduced baselines, baseline failures, probe trials, changed-outcome trials/clips and exceptions.

No PPO, no changes to the 71 `.npz` files, no Cycle 9 or champion checkpoint modifications. Avoid starting old `train_scenarios.py`: its environment still terminates before the verified tail and uses a longer unverified replay segment.
