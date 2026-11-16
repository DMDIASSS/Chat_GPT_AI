# DuelForge 0.3 update

Read **UPDATE_0_3.md** first. For the new experiment use **17_START_LEARNING_V2.bat**, **18_WATCH_LEARNING_V2.bat**, and **19_REPORT_LEARNING_V2.bat**. Existing duel01 resumes with its original settings.

# DuelForge 0.2 — extended test prototype

A fresh Octane 1v1 bot with native RocketSim collection and a 1,216,091-parameter dense actor/critic. Includes bounded training, full checkpoints, history self-play, optional Nexto, actual gameplay viewing, a frame inspector, evaluation, reports and RLBot v5 export.

**This is a working research prototype, not a pretrained competitive bot.** No old project weights are included. Short training tests establish pipeline correctness; playing strength after hours or days is unverified.

## Install and first test

1. Extract the ZIP into `E:\Downloads` so the project is `E:\Downloads\chat_gpt_ai\duelforge`. Windows treats `chat_gpt_ai` and `Chat_GPT_AI` as the same folder. If your extraction program adds another outer folder, move the included `duelforge` folder into your existing `Chat_GPT_AI` folder. Existing Gigaforge and AttentionForge projects remain separate.
2. Close other trainers. Run **0_SETUP.bat** once. It finds an existing 64-bit Python 3.11 with Torch/NumPy, prefers CUDA, reuses Soccar collision meshes, and checks native/Python feature and action agreement. It does not install or move CUDA/Torch. Check the printed runtime, CUDA device and `VERIFY_PASS`.
3. Open **DUELFORGE.bat**, choose **1**. The first start creates a fresh model in `runs/duel01`; later starts resume its model, Adam state and counters. Each session saves and stops after about 60 minutes. Finish the current rollout/update before expecting a pause to complete.
4. For a first behavior check, train for **10–15 minutes**, then use **2_PAUSE.bat** in another console, or press Ctrl+C in training. Wait for `PAUSED_AND_SAVED`. The menu's choice 2 is useful when the trainer is in another console; the training menu itself is occupied while it trains.
5. In the menu choose **3** to watch kickoffs or **4** to watch open play. **Blue is your learned policy; orange is its frozen random initial policy. Both are Octane.** No training happens during watch. Both being poor at first is expected; orange is a control, not a teacher.
6. Choose **8** for the last recording's frame inspector: scrub real simulated poses, actions, contacts, ball velocity/spin, policy probabilities, critic estimate and reward components. The inspector opens through a local loopback server; press Enter in its console when finished.
7. Choose **5** for a quick balanced-color validation panel, then **6** to make a report ZIP. Send the `DuelForge_report_duel01_*.zip` with your gameplay observations. Reports omit weights, credentials, W&B files and environments.

Judge early changes by ball contacts, useful movement and open-play interaction. A win against the initial random policy does not establish strong play. You can resume another bounded session without reinstalling. Do not leave multiple trainers running together on the laptop.

## Viewer and stronger opponent

Watch uses **RocketSimVis** and actual live simulation, not replay playback. An existing nearby viewer is reused; otherwise its pinned source and GUI-only dependencies are installed once in `third_party/RocketSimVis/.venv`. Torch/CUDA are untouched. FOV 110, distance 270, height 100 are set in the launched viewer. A viewer startup error is printed instead of silently running an invisible match. The browser frame inspector is also available separately from the 3D window.

Menu **10** downloads checksum-verified Nexto assets. **11** watches against Nexto, and **12** evaluates against it. This uses Nexto's neural controls, with its stock scripted kickoff disabled. Nexto remains frozen. Default training does not use it. **13** creates a separate `duel01_nexto` fork with 20% Nexto opponent assignments and resumes that fork; it preserves `duel01`. To reopen that fork's menu, run `_RUN.bat menu --run duel01_nexto`.

The optional **14** runs six sequential ten-minute A/B training blocks with three paired initialization seeds, contact-impulse reward 0 versus 0.05, within a 90-minute session budget. It tests an early-learning hypothesis, not a strong-bot claim. Normal start is the simpler first test.

## Export

After pausing, choose **7**. A unique folder is created under `exports/` with `actor.lt`, `actor.pt`, both TOMLs and the Python inference wrapper. Run that folder's **INSTALL_V5.bat** once, then **DIAGNOSE_V5.bat**, and import **bot.portable.bot.toml** into RLBot v5 for a normal 1v1 match. The isolated wrapper reuses existing Torch/NumPy when available; on another PC it can install CPU inference dependencies. Export does not need a running trainer.

Here `.lt` and `.pt` are TorchScript read by the included wrapper. They are not GGL native parameter archives and must not be dropped into a different bot's reader. RLBot v4 `.cfg` is not included in this prototype. Source/PT/LT logits and selected actions are checked at export. The SDK, packet conversion and action clock were tested; an actual Rocket League game-client match must still be tested on your PC.

## Logs, evaluation and configuration

Local `metrics.jsonl` includes real learner transitions/s, collection/PPO time, goals, contacts, reward sums, KL, entropy, backward/airborne fractions and memory. W&B uses the SDK's existing login if available, in a new `duelforge` project; local logging continues without it. No keys are collected in reports.

Training starts with mixed kickoff and varied ground states. Default rewards are goal ±1, a small goal-progress potential difference and a contact-gated ball-impulse bonus. They are new experimental hypotheses, not recovered Chronos/Galactus training rewards. There is no scripted driving, kickoff, half-flip or aerial controller. Details and failure modes are in **PROTOTYPE_GUIDE.md** and **ARCHITECTURE.md**.

Configs are frozen per run. Change root `config.json` only for a new run: `_RUN.bat train --run experiment02 --minutes 60`. Never silently alter an existing run. Exact model/config/hash records and full optimizer checkpoints are preserved. Physics restarts on resume; resume is not bit-for-bit continuation of an in-flight episode.

Automatic validation every approximately one million learner transitions uses a small discovery panel against the initial model. Menu **15** watches the exact pinned best open-play validation candidate; it is unverified. Menu **16** runs 2,000 fresh paired-color games, 100 simulated seconds each, against the frozen initial policy. Draws score half, and 95% intervals use seed-pair blocks. No candidate silently replaces another model, and repeated validation is not an independent strength confirmation.

## Verification and development

**VALIDATION.json** records what ran here, including a Windows native build/import/parity job, 29 tests, a full-size bounded CPU training check and browser inspector checks. This server has no CUDA or Rocket League client; local GPU throughput, thermals, 3D GUI startup and live RLBot deployment remain local checks. CPU rates and synthetic GPU examples/s are not interchangeable.

The included Windows native extension is for **CPython 3.11, Windows x64**. See **BUILD_NATIVE.md** for reproducible native source builds. `python -m pytest -q tests` runs the tests with Torch, NumPy, pytest, the native module and existing Soccar meshes; Nexto/SDK checks require those optional dependencies. `research/PHASE1_ARCHITECTURE.md` and the source audit are historical research records; this README describes the implemented version.
