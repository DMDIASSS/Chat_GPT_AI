# Finishing Lab v1 — isolated shooting experiment for Chat_GPT_AI

**Important:** This add-on is experimental. It has passed pure-Python tests but hasn't been run
against a real RocketSim installation in the authoring environment. It does not magically
teach double taps or flicks. It tests physics-based **proxies** that require manual validation.

## Why this upgrade exists

On the held-out tournament Cycle 9 looked competitive against Nexto but the player reports
high aggression with poor shot accuracy. The earlier 40-pair kickoff diagnostic only had
**5 unique kickoff starts**, and its 90-decision cap produced **80/80 draws** for each
matchup; that is not useful evidence about shot accuracy.

We want selective finishing: take direct shots when the lane is open; otherwise
retain pressure, flick around a defender or create a useful backboard follow-up.
Do **not** reward throwing every ball toward goal, air time or flashy moves alone.

## Install

1. STOP `AUTO_1_START`, AFK training, and all diagnostic/training windows.
2. Make a normal backup of `data/autoleague/champion.pt` and `league_state.json`.
3. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`, next to `auto_league.py`.
   These are new files; no existing Python scripts need replacing.
4. Run `FINISH_0_CHECK.bat` (actual RocketSim + model preflight).
5. Run `FINISH_1_SMOKE.bat` (isolated 96 training decisions and short evaluation).
6. Run `FINISH_4_SHOT_BENCHMARK.bat` **before** training, to establish the baseline.
7. When the smoke and benchmark work, run `FINISH_2_TRAIN.bat`.
8. After training, run `FINISH_4_SHOT_BENCHMARK.bat` and `FINISH_3_EVAL.bat`.
   Then share the new JSON report files.

There is **no automatic model promotion**. The original AutoLeague champion is not changed.
All trained experiment weights live in `data/finishing_lab/candidate.pt`, logs and results
under `data/finishing_lab`. Smoke training uses `data/finishing_lab_smoke` instead.

## What training does

- Starts with an exact SHA-checked Cycle 9 candidate `50f34d4a3723...`.
- Uses the project's actual native Nexto actor, observation pipeline and 90-action space.
- Reuses the existing AutoLeague PPO + self-play logic **in memory**; its on-disk code is unchanged.
- Rotates randomized ground finishes, dribble/flick opportunities, backboard approaches,
  and blocked-lane situations. Approximately 25% of training resets still use standard kickoffs.
- Keeps genuine goals (±10) much more valuable than conditional shaping (maximum +0.21
  on rare touchdown events).
- Gives **no** extra bonus for touching the ball, hitting a backboard alone, or performing
  a flip without an on-target release.
- Gives small credit when a release's approximate gravity-only path is on target, and
  reduces that credit when an opponent appears to occupy the shooting lane.
- Gives a conditional *second-touch* bonus after an observed high back-wall rebound
  **only if** the second touch releases a ball that approximately enters the goal mouth.
- Uses actor learning rate `1e-6`, anchoring to unchanged Cycle 9 with KL weight `1.0`
  to reduce forgetting, but that DOES NOT guarantee performance won't regress.
- Checkpoints after each rollout; rerunning `FINISH_2_TRAIN.bat` resumes from the last
  saved checkpoint. If stopped mid-rollout, only that unsaved rollout is lost.
- Evaluates versus Cycle 9 and Nexto after the training target is reached, using the
  ordinary AutoLeague held-out first-goal evaluation (not five-minute matches).

## Evaluator limitations

- `forward_release_proxy` and `off_target_forward_release_proxy`: cooldown-deduplicated
  forward ball launches, and those whose simple predicted trajectory misses the mouth.
  **These cannot determine whether a tactical backboard pass was actually good.**
- `direct_on_target_proxy`: gravity-only predicted ball crossing the opponent goal mouth
  (x and z bounds). Not an actual shot-on-target stat; fails to predict bounces or saves.
- `backboard_bounce_proxy`: estimated back-wall speed reversal after one of our touches.
- `followup_on_target_proxy`: an estimated second touch after the wall that aims toward goal.
- `flick_on_target_proxy`: a flipping touch that has an approximate on-target release.
  **Does not verify the mechanics of a real dribble flick.**
- The 1v1 match episodes cap after 22–30 simulated seconds or first goal; they are not
  full five-minute competitive matches.
- Scenario starts are randomized and side-mirrored, but synthesized rather than replay-derived.
- Shoot proxies are for **diagnostics and weak reward shaping**. Decide if a model is better
  using held-out wins, head-to-head and visual gameplay, not only these counters.

If the first smoke test fails, do not keep starting the full trainer. Send the console output.
Never copy `data/finishing_lab/candidate.pt` over `data/autoleague/champion.pt` without a
separate independent evaluation and backup.

## Important licensing

The original Nexto model files are under their upstream license (CC BY-NC-SA as described
in project sources). Preserve their license when distributing derived checkpoints.
