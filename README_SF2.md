# Chat GPT AI — SkillForge Visual Fix v2

**Why this patch exists:** The old visual-debug scenario put the ball off the car's line, spawned a second idle car, and used a fixed-tick dodge macro that tended to flip too early. The ordinary-flip reference was deliberately just a flip. None of that showed meaningful movement toward a target.

**Safety:** This patch is calibration/visualization only. It neither reads nor modifies `data/native_nexto/*.pt`, `data/mechanics/*.pt`, or the original SkillForge v1 experiment files. Your `best_10k.pt` and `kickoff/last.pt` stay unchanged. It does **not** train an AI yet.

## Install

Extract this ZIP directly inside `E:\Downloads\Chat_GPT_AI` (same folder as `.venv`). It adds files named `sf2_*` and `SF2_*`, so nothing from v1 is replaced.

## Run, in order

1. **`SF2_0_PREFLIGHT.bat`** — checks with REAL RocketSim that there is **exactly one** car, it faces and moves **toward** the ball, and its scripted controller can trigger a dodge. This check does not require a real wavedash success. **If it fails, stop and send the log.**
2. **`SF2_1_WATCH_TIMED_DASH.bat`** — runs one blue car, a ball straight ahead (visual reference only), slow-motion time, and logs exact dodge/landing ticks. Press **Esc**, then **1** to follow the car in RLViser. This is a scripted test, not an AI playing a match.
3. **`SF2_2_SEARCH_TIMING.bat`** — if the viewer looks physically sensible, tries 84 combinations of ground-trigger height, nose pitch, and pitch-cancel duration against four varied starts. Runs a separate 16-spawn holdout. This **does not train Nexto** and does not call anything mastered automatically.
4. **`SF2_3_WATCH_SEARCH_RESULT.bat`** — watches the best saved search sequence. It may still be a failure: read the result and trace.

For comparing an obviously-too-early dodge with a later dodge, run `SF2_COMPARE_EARLY_LATE.bat`.

The search saves `data\skillforge_v2\calibration.json` and the viewer saves `data\skillforge_v2\viewer_trace.csv`; v1 results are untouched. If repeating a search, rename/move that calibration file or run `sf2_search.py --overwrite` intentionally.

## What qualifies as a wavedash candidate?

Aerial dodge while descending, collision with at least three wheels within **10 physics ticks** of the dodge, upright stabilization and forward speed gain without throttle, boost or steering. The detector rejects long airborne flips and excessive rotation. **These are provisional physics checks**, not proof of a genuine optimal wavedash: the visual replay matters, and the decoder can still have edge cases. Even a passing script is only a demonstration, not a learned policy.

The user observation that a real wavedash **cancels a dodge on landing rather than completing a 360-degree flip** is incorporated in the detector. Critically, the dodge input must be initiated *before* ground contact; pressing jump after the car is already grounded starts a new jump, not a wavedash.

## Why the old replay looked strange

- **Flying away from ball**: ball was intentionally placed off-path by SkillForge v1.
- **Two AI cars**: v1 created a blue and orange car, but the second one was a stationary dummy; neither was actually your trained Nexto in this diagnostic.
- **Clipping into ground**: visual interpolation, unusual starting state or a real collision issue are all possible. The new viewer records `center_z`, wheel contacts, and orientation every tick. If it still appears to go through the field, send the CSV or last printed values. A car *center* below zero indicates a much more serious simulation issue; do not assume this from the image alone.
- **`DODGE_CONTROL` spun**: it intentionally tested an early un-canceled dodge. It was not intended to be the finished wavedash.

## Development / tests

`python -m pytest -q tests/test_sf2.py` checks script controls, relative ball placement, detector logic (including the fact that RocketSim may reset `has_flipped` immediately on contact), and search/viewer behavior in **mock simulation**. Real physics and RLViser rendering must be verified by the `.bat` files on Windows.
