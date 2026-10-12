# Slater v0.1.4 — Shot flight diagnostics (read-only)

## Why the prior fidelity results failed

Five *full-clip* reproductions failed from 12-second approximate replay-derived controls. Scores and the ball positions can diverge strongly over 12 seconds even with genuine RocketSim, especially with kinematic ghost cars. The original five goal clips also came from the same replay. One simulation scored before the reference goal step, which was represented by `Infinity` rather than a valid measured error.

**Do not use the 71 candidate clips for PPO training yet.** This audit is diagnostic only and does **not** fix their fidelity; it investigates *where* the drift starts and whether a short terminal shot flight is reproducible.

## Install

Extract this ZIP into `E:\Downloads\Chat_GPT_AI` and merge `slater_research`. Preserve the existing v0.1.3 installation; this adds `flight_audit.py` and a test without changing the original checkpoint or dataset files.

## Run in Windows CMD

```
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.flight_audit --clips data\replay_scenarios_smoke_v012 --limit 5 --windows 0.25,0.5,1,2 --out data\replay_scenarios_smoke_v012\flight_audit_v014_sample5.json
```

The new tool samples different source replays, not just the first five files, and independently tests 0.25, 0.5, 1 and 2 seconds before the reference goal. It compares (a) attacker car replay-ghosted with defenders dynamically simulated and (b) all cars fully simulated with replay-inferred controls. The ball is always dynamic. Fields include `ball_error_uu_after_first_step`, `ball_error_uu_at_stop`, `ball_error_uu_at_reference_goal`, `early_goal_unverifiable`, `first_step_above_threshold`, `actual_goal_step`, and whether the scored goal matches the original team.

A short-horizon successful case **does not** prove a trustworthy 12-second replay, and neither mode is perfect ground truth. A failed goal at reference frame may also be due to goal events occurring a few physics ticks after the final saved sample. Do not loosen the 250-uu limit just to fabricate a pass. Do not delete the original data or rerun training.

Upload `flight_audit_v014_sample5.json` and the CMD output. If even 0.25–0.5-second windows fail with huge errors, next inspect goal-frame labeling / serialization or contact transitions. If short windows reproduce well, next build *launch-state* defensive scenarios from the post-hit ball state and validate them over the exact shot-flight horizon instead of forcing long open-loop replay control reconstruction.
