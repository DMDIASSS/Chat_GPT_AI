# Slater goal tail audit v0.1.5 — endpoint-aware short-horizon verification

## Analysis of the actual uploaded data

- In the supplied v0.1.4 flight report, 0.25-s endpoint trajectories matched to within 250 uu for **10/10** runs (5 source replays × 2 simulator modes). 0.5-s windows matched 9/10, 1-s 8/10, and 2-s only 3/10 by endpoint error (2/10 for maximum error along the full window).
- RLGym's RocketSimEngine computes `goal_scored` as `abs(ball.position[1]) > GOAL_THRESHOLD`, with `GOAL_THRESHOLD=5215.5` in standard soccar.
- **All 17** provided `bf6fc…` / `cf3e…` NPZ clips save a terminal reference state with `abs(ball.y) <= 5215.5`. Their `goal_step` is therefore **not the physics goal-trigger step** even though the source replay labels the impending goal. This makes `scored=False` at the final saved sample unsurprising.
- Longer reconstructions *do* diverge. This package does not claim the original 12-second trajectories are reliable.

## Install

Extract `slater_research_goal_tail_v015.zip` into the root of `E:\Downloads\Chat_GPT_AI` and merge the `slater_research` directory. It adds `goal_tail_audit.py`, `tests/test_goal_tail_audit.py` and this README. It does not overwrite the earlier training, checkpoint, replay-engine, or other audit files.

## Run from **Windows CMD**

```cmd
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.goal_tail_audit --clips data\replay_scenarios_smoke_v012 --limit 10 --windows 0.25,0.5,1,2 --post-seconds 0.3 --out data\replay_scenarios_smoke_v012\goal_tail_v015_10.json
```

### Scoring criteria

`endpoint_position_matched`: ball location at the final **recorded** sample differs by at most 250 uu.

`entire_reference_window_matched`: every sample during the 0.25/0.5/1/2-second reference window stays within 250 uu.

`verified_goal_by_deadline`: RocketSim's own goal event is detected for the right team at or within the bounded post-clip tail. The post-rollout does **not** teleport the ball or ghost cars. It continues all cars dynamically using the last inferred controls; the default 0.3-second limit gives **4** decision steps × 8 physics ticks = approximately **0.267 seconds** after the final recorded sample.

`accepted`: all three checks pass without any goal occurring *before* the recorded goal frame. Early simulator goals stay marked as unverifiable.

**Warning:** matching the final ball position and scoring immediately afterwards is only a *short-horizon baseline test*. It does not prove the 10–15-second recorded shooter controller sequence can be replayed physically, and it does not validate the counterfactual defender-training mode. Do not promote checkpoints or start PPO from these scenarios before the short-goal baseline has been reviewed.

## Important next scientific milestone

If several 0.25–0.5-s windows pass with verified goals, build scenario start states from **just after the final recorded attacking ball touch** (the start of free flight), and check if the ball scores without further opponent contact. Then construct defender perturbations to block that reliable **launch-state baseline**. Preserve held-out source replays and run 1v1, 2v2, 3v3 evaluations separately. Your tested data directory `ranked-duels` currently represents 1v1, not teamplay.

## Test notes

The new math, guardrails, and a mocked physics-step continuation path pass local tests; overall unit suite: **34 passed**. Live RocketSim verification on your Windows PC is not yet complete. No `.pt` files are loaded or modified.
