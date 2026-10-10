# GigaLearn Research Hub — Gameplay Evaluator v1

## What it does

A **read-only**, real RocketSim **1v1 first-goal evaluator** for your GigaLearn `.lt` checkpoints. No retraining, no checkpoint promotion, no native Nexto `.pt` conversion. Uses GigaLearn's native `InferUnit` and the same `AdvancedObs`, `DefaultAction`, network architecture, tick skip (8), and action delay (7) as the research trainer.

- Seeded kickoff: each seed is played **twice** with the policies assigned to opposite teams. RocketSim's `ResetToRandomKickoff(seed)` makes the kickoff layout repeatable.
- Stops on the first goal or a configurable decision cap (draw).
- Reports model A W/L/D, paired-score percentage, shot events, save events, ball touches, demo events, and mean/peak ball speed.
- A 3-model round robin aggregates results without claiming universal improvement. In particular, short first-goal experiments are not full five-minute match win rates.
- App tab: **Gameplay Eval**; also includes command-line scripts.
- Matches use **greedy/deterministic** discrete actions by default, CPU inference by default. You can use `--gpu` via Python if you choose.

**Limitations:** Only 1v1 models with the archived 256/256 shared head and 256/256/256 policy architecture. Not the Nexto `.pt` models. Not compatible with `defensev1` 1v2 weights. Not full-game evaluation; goalkeeper accuracy, wall mechanics, 1v2 scenarios, and penalty-shootout testing require separate evaluation suites. No auto-promotion. Results should be replicated with several new seed sets.

## Safe Windows installation

1. Close Research Hub and safely stop active training. **Back up `GigaLearn_Project`**, particularly `Research_Hub/experiments` and `build_py311/checkpoints`. This add-on contains **no model weights**.
2. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`. It creates new files under `GigaLearn_Project\Research_Hub`. It does not contain `hub_app.py`, `hub_core.py` or other existing files.
3. Run `Research_Hub\EVAL_0_CHECK.bat`. It should discover `smoke_balanced_01`, `shootingv1`, `defense1v1`. If it does not, check names, experiment locations and checkpoint availability.
4. Run `Research_Hub\EVAL_1_PATCH_CPP.bat`. The installer backs up and patches the **existing** `upstream/CMakeLists.txt`, installs a new `upstream/src/HubEvaluate.cpp`, and adds a **Gameplay Eval** tab while backing up your original `hub_app.py`. It is repeat-safe.
5. Open **x64 Native Tools Command Prompt for VS 2022**, then:

   ```cmd
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub
   EVAL_2_BUILD.bat
   ```

   This invokes CMake and builds **GigaLearnEval.exe**, independent of `GigaLearnBot.exe`. It uses your existing `build_py311` configuration. This build must succeed before evaluation.
6. Run `EVAL_3_SMOKE.bat` (2 paired kickoff seeds, low decision cap). First verify checkpoint loading and both sides simulating correctly. If it fails, send the full output/log; do not rerun training.
7. Restart Research Hub, open **Gameplay Eval**, select Balanced, Shooting and Defense, and click **Run paired tournament**. Try `4` pairs and `600` decisions first; then `20–40+` pairs and `900` decisions (can take much longer). Or run `EVAL_4_THREE_MODEL.bat` for a longer comparison.

## Reports

Results are saved to **new timestamped folders**:

`Research_Hub\evaluations\YYYYMMDDTHHMMSSZ_<id>\`

Each match has `match_XX.json` and `match_XX.log`. `summary.json` contains an aggregated standings table. `last_report_path.txt` points at the latest successful summary. Failed runs have a `FAILED.txt`. No training checkpoint is changed.

After evaluating, run:

```cmd
"C:\Users\almas\AppData\Local\Programs\Python\Python311\python.exe" hub_eval.py --last
```

## Fairness and interpretation

Your metadata confirms `shootingv1` and `defense1v1` both began from **the same** `smoke_balanced_01\checkpoints\2398176`, with matching hashes for `POLICY.lt`, `SHARED_HEAD.lt`, critic, optimizers, and stats. This is a clean comparison of training branches, but it does not guarantee that the reward changes helped. More timesteps does not equal higher skill. Perform side-swapped held-out kickoffs, and then test different goals/shooting/defending scenarios before calling a model better.

The initial trainer played with sampled actions; this evaluator uses deterministic argmax actions, so behavior can differ. All participants use the same evaluator settings. Shot/save counts come from RocketSim's event tracker, not human-labeled shot accuracy.

## Verification status

Automated **Python** safety, report-aggregation, no-overwrite, patch-idempotence and model-selection tests pass. The C++ evaluator uses real upstream APIs, but this package **has not been compiled or run under Windows/MSVC/RocketSim here**. The first build and smoke run may uncover a compatibility issue requiring a follow-up patch. Report the exact error; do not alter your working GigaLearnBot trainer to fix the evaluator.
