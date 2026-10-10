# AFK Improved v2.3 — Research expansion

**Read before installing.** Tested on local CPU TorchScript and mocked multi-car states; **not yet tested** with real RocketSim, RLBot v4 runtime, or Windows GUI in this build environment. No files in this ZIP include model weights or user data.

## Install order

1. Stop **all** AFK, LEARN_ONE_CLICK, and Aggressive Research processes. Don't interrupt an active PPO cycle before it safely checkpoints.
2. Back up your current `afk_improved_app.py`, `export_rlbot_v4.py`, and `afk_replay_tas_learning.py` somewhere outside the folder (plus precious `data/` backups if you can).
3. Extract this ZIP over `E:\Downloads\Chat_GPT_AI` and allow replacement of the **three code files only**. No original weights, checkpoints, saved PPO history, or replay data are shipped or overwritten.
4. This upgrade assumes you previously installed **AFK Improved v2.1**, **Replay + TAS Learning v1**, and **Aggressive Research v1**. It preserves the existing app's other tabs.
5. Launch `AFK_IMPROVED_DESKTOP.vbs` again.
6. Separately extract `GigaLearn_Project.zip` into the main folder: `Chat_GPT_AI\GigaLearn_Project\`.

## New UI and features

- **Viewer & RLBot**: select any existing **native Nexto** checkpoint using Browse; name the RLBot v4 export. Every export is a unique new folder in `data/rlbot_exports/`. Previous exports and .pt originals are never overwritten. **Experimental AFK cycle-9 candidate** is usually in `data/afk_improved/league/inconclusive/`. Pick its exact `.pt`, not the original Cycle 9 file. Native actor checkpoints only: older 92-input student PPO is incompatible.
- The exporter copies the original upstream v4 adapter with its license and verifies TorchScript state tensors after saving. **RLBot v4 only**; the current RLBot v5 API has not been ported. Do not run bots in online public queues.
- **Team modes**: multi-car attention observations are padded to six players. A shared learner policy controls 1–3 teammates versus 1–3 frozen Nexto opponents. Modes 1v2, 1v3, 2v2, 2v3, 3v2, 3v3 and their mirrors are supported by the experimental simulator code. `kickoff`, `grounded`, and **defensive pressure** scenarios. `mixed` is for held-out evaluation. PPO research checkpoints are written only to `data/afk_improved/team_research/`, not to AutoLeague champion.
- **Mechanics Lab**: exposes the existing project `mechanics_train.py` with an isolated Cycle 9 checkpoint location and evaluation. Recovery, wavedash, kickoff, aerial touch, etc. **Not a 120-Hz walldash controller**. Does not automatically merge mechanics models.
- **Replay + TAS Learning**: replay hyperparameter sweeps using the **existing** cached `native_replay_dataset.npz`; distinct branches use separate experiment dirs and source hashes. This is a safer next step following the previous rejected candidate. Original action reconstruction quality is still approximate. TAS inputs are still **audit-only**, not fake imitation examples.

## First safe test commands

```bat
TEAM_0_PREFLIGHT_1v2.bat
```

If the real multi-car RocketSim observation test succeeds, choose Team modes in the app, 1 our player / 2 opponents, pressure, **512 samples**. Or use:

```bat
TEAM_1_SMOKE_TRAIN_1v2.bat
```

It writes a **new, unverified candidate**; run held-out Team evaluation (pick that checkpoint) before trusting it. Change seed or mode to do another experiment; existing files are never replaced.

For replay learning, run:

```bat
REPLAY_SWEEP_0_CHECK.bat
REPLAY_SWEEP_1_START.bat
REPLAY_SWEEP_2_REPORT.bat
```

If `small_step` produced an accepted **offline-only** candidate:

```bat
REPLAY_SWEEP_3_VERIFY.bat
```

Only a separate RocketSim competitive evaluation can establish whether it's better; even then, test diverse starts and longer matches. A lower offline cross-entropy is not necessarily better gameplay. The code does **not** auto-promote.

## Limitations and safety

- Multi-car RocketSim engine compatibility and training stability need Windows preflight; observation shape and real Nexto TorchScript forward were checked for 2..6 cars **with synthetic states**.
- No true tactical role assignment, passing skill controller, contextual bumps/demos, speedflip/fake kickoff switcher, 120 Hz wall-dash, RLBot v5, verified training in GigaLearn C++, or TAS-to-native alignment yet. The defensive pressure curriculum is a first honest step toward 1v2/1v3 learning, not an already strong 1v3 bot.
- Running an ordinary Replay Learning job and replay sweep concurrently is prevented by an OS-held lock. Avoid launching Team/Mechanics/Research training simultaneously: they consume the same CPU and the separate trainers are not a unified scheduler.
- **CUDA**: For the current bundled Nexto TorchScript, choose CPU. GigaLearn C++ is independent and typically expects NVIDIA CUDA.
- Derived Nexto models/code may have noncommercial license restrictions; preserve upstream licenses when redistributing.
