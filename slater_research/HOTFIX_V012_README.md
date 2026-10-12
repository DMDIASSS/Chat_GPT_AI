# Replay extraction hotfix v0.1.2

**Apply this incremental patch on top of v0.1.1**. Extract into `E:\Downloads\Chat_GPT_AI`, allowing overwrite of matching files. The patch does not modify checkpoints or the main project training scripts.

## Problem

The smoke test detected real goal periods but rejected all goal clips with `invalid_or_stale_replay_frames`. `replay_to_rlgym` computes a replay state's `tick_count` from the replay timestamp * 120, which may be non-integer. The previous extractor calculated `tick0 = int(tick_count)`, rounding the first tick down. That sampled a timestamp before the first available frame and immediately failed the `i < start` guard for otherwise eligible clips.

## Changes

- Align sampling to the **first physics tick at or after** the initial replay frame (`ceil(time*120)`), maintaining exact eight-tick action intervals.
- Stop at the actual goal boundary, not the next kickoff.
- Cap goal-step indices to exported frames.
- Differentiate `timestamp_outside_clip`, `time_gap_over_110ms`, `frame_serialization_failed`, and `invalid_controls`, including the first failing timestamp/error in diagnostics. This does **not** relax the frame staleness threshold.
- Regression-test fractional tick timestamps. Local suite: 15 passed.

## Windows CMD commands (no inline comments)

```cmd
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.extract --replays data\replays --out data\replay_scenarios_smoke_v012 --lead 12 --limit 10
```

Expect at least some clips if frame sampling was the only remaining issue; this **has not been verified on the user's replay files**. If still 0, send full output including `example_failure`, plus the resulting `manifest.json`. Never start PPO on zero or unvalidated clips. Next step after successful export is an independent RocketSim fidelity check.
