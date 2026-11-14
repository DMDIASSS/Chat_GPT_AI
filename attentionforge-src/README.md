# AttentionForge 0.2 laptop update

Start with **[LAPTOP_UPDATE.md](LAPTOP_UPDATE.md)** for the new 1.09M-parameter run, native standard rewards and laptop timing probes. Open **LAPTOP.bat**. Existing `attention01` launchers/runs remain available.

The original 0.1 instructions below describe the legacy 76k run.

# AttentionForge 0.1 — a fresh attention bot

This is a separate project. It does not use Chronos, Galactus, RocketHive, replay retrieval, a selector, pretrained weights or GigaLearn's MLP trainer. It starts with a random **76,251-parameter attention policy**, learns through native RocketSim self-play, and uses batched PyTorch PPO. It reuses an existing Python/CUDA installation and collision meshes when available. It never starts an old trainer.

## Start on your Windows laptop

1. Close/pause old trainers. Extract the ZIP into **E:\Downloads**, producing **E:\Downloads\chat_gpt_ai\attention_forge**. Windows merges `chat_gpt_ai` with your existing `Chat_GPT_AI`. Alternatively, copy just `attention_forge` into your existing `Chat_GPT_AI` folder. Do not extract `chat_gpt_ai` inside `Chat_GPT_AI`.
2. Open `attention_forge` and run **SETUP.bat**. It prefers `gigaforge\.venv_native\Scripts\python.exe` with CUDA; then checks the existing RocketHive/NovaForge environments. No working Torch/CUDA installation is replaced. The supplied native module requires **Python 3.11 x64**. Wait for `VERIFY_PASS` and `SETUP_READY`.
3. Run **BENCHMARK.bat**. It measures simulation + public observation encoding + attention inference. These are player decisions, not PPO learning throughput or game physics ticks. Share `benchmark.json` if it is unexpectedly slow.
4. Run **START_OR_RESUME.bat**. A **new** `runs\attention01` starts from random weights. Keep this window open. A second trainer for the same run is rejected. The console shows touches, goals, approximate KL and **end-to-end learning transitions/s including PPO** after each update.
5. For the first check, run **30–60 minutes**, then **PAUSE.bat**. Wait until the trainer prints `PAUSED_AND_SAVED`. Checkpoints also save every two minutes. Ctrl+C requests the same graceful save. Resume with `START_OR_RESUME.bat`.
6. Run **WATCH.bat** after pausing. It shows **latest policy blue vs the same policy orange, both Octane**, at real-time speed (FOV 110, distance 270, height 100; viewer-native ball camera). If RocketSimVis is not already installed by RocketHive, run **SETUP_VIEWER.bat** once, then WATCH. This viewer uses its own GUI environment; a missing/failed viewer is reported. Watching never trains. Ctrl+C stops viewing.
7. Run **REPORT.bat**, then send the resulting **AttentionForge_report_*.zip**. It includes config, source, runtime details, hashes, metrics and evaluations, with no weights, login keys or W&B files. A weak bot after an hour is not evidence that it can never learn; a broken reward/contract or no improvement across longer runs needs investigation.

If meshes are missing, add `local_paths.json` containing `{"meshes":"E:/your/path/collision_meshes"}` or set `ATTENTIONFORGE_MESHES`. Use the folder that contains `soccar/*.cmf`. Meshes from your installed `rlgym.rocket_league.sim` are automatically reused. No Rocket League game assets are included in this ZIP.

## What trains

- Standard Soccar, **1v1 Octane**, physics 120Hz, policy decision every eight ticks (**15Hz**), one-tick controller delay for both teams. No scripted kickoff controller, teacher policy, search or hindsight inputs.
- Each observation has 43 typed entities: ego, ball, up to two allies, up to three opponents, 34 boost pads and two goals. Missing cars are padded. Features include relative position/velocity, angular velocity, car attitude, boost, jump/contact flags, team-normalized field position, and only the ego's previous controls. Ball orientation and opponents' actual controls are excluded.
- Two ego-query attention blocks, width 64, four heads, dropout zero; 90 discrete controller choices; a scalar value head. No giant transformer or replay memorization.
- Half of resets are ordinary kickoffs. Half are randomized ground states near the ball, with random car yaw and boost, to make early contacts discoverable. A goal ends the episode. Sixty-second episodes and 15-second no-touch limits truncate with **final-state value bootstrapping**. After resets the policy receives fresh state.
- PPO: 256 decisions/arena per rollout, 32 arenas, two epochs, minibatches 512, Adam 3e-4, gamma .995 at 15Hz, GAE .95, clipping .2, entropy .01, gradient clipping .5 and a KL early stop. Rollouts stay in host memory; minibatches go to the GPU. Default CPU budgets: four native workers, two Torch threads. Settings are in `config.json`.
- Current-policy self-play initially. Every one million **learning transitions**, save a frozen historical opponent. Once available, about 25% of arenas train against one frozen opponent sampled for the rollout. Other arenas use current-policy self-play. Frozen players' actions are excluded from the PPO loss. Opponent weights use `(1 - smoothed_goal_exchange_score)^2 + .05`; this is a difficulty heuristic from goal exchanges, **not match W/D/L**. Keep at most eight rotating history snapshots. The first snapshot is also pinned permanently as `baseline.pt` for repeatable progress checks.
- The native interface supports balanced team sizes 1–3, but **only 1v1 is the default validated training path**. No automatic move to 2v2/3v3, team hivemind or team-strength claim is made.

## Exactly which rewards

These are our explicit starting hypotheses, **not the unknown possession formula from the Discord post**. A reward is not a guarantee of strength. All components are team-shared and zero-sum between teams.

| Component | Formula, from blue's perspective | Default |
|---|---|---:|
| Goal | +weight for blue scoring; -weight for orange scoring | 10 |
| Approach potential | `weight * (gamma * next_phi - current_phi)`, where `phi = max_blue exp(-distance_to_ball/1500) - max_orange exp(-distance_to_ball/1500)`; demoed cars contribute zero, terminal next potential is zero | 2 |
| Fresh touch | Difference in credited team touches; .25s cooldown per car, at most one credited touch/team/decision | .02 |
| Controlled attacking progress | `weight * dt * (blue_control - orange_control)`. Per car, control is `clip(1-distance/600,0,1) * exp(-relative_speed/800) * clip(ball_velocity_toward_enemy_goal/2300,0,1)`; use the team's maximum | .2/second |

Control progress is zero for a motionless ball; there is no reward just for parking beside it. There are no rewards for arbitrary flips, boosting, driving fast or being airborne. Goal rewards are enabled from the first update. Approach shaping has the discounted-potential form; its useful learning effect and the other dense terms still need empirical evaluation. They can introduce unwanted incentives, so track actual goals and held-out matches separately.

## Progress and evaluation

Pause first, wait for `PAUSED_AND_SAVED`, then use **EVALUATE.bat** after there is a pinned baseline: 100 fresh-seed 60-second games against the first frozen checkpoint, balanced between colors. It never trains or promotes a bot. A report includes per-game goals, seeds, actor hashes and a conservative 95% interval using two-color seed blocks. This measures progress against that fixed early model; **it does not establish Nexto/Galactus strength**. No overtime. Timeout can overshoot by at most seven physics ticks.

For a larger frozen comparison:

```bat
_RUN.bat evaluate --run attention01 --rounds 500 --seconds 100
```

To compare with a particular AttentionForge checkpoint, add `--opponent "path\to\checkpoint.pt"`. These are native AttentionForge models only; arbitrary botpack `.lt` models are not compatible with this observation/action contract. Evaluation seeds are generated separately from the training seed; held-out matches are not fed back into PPO or opponent weighting. Do not repeatedly tune on a final test panel and then call it held-out.

Watch **touches per unit of simulated time**, distance to the ball, actual goal frequency, action diversity and frozen-opponent scores. Self-play reward or speed alone does not prove improvement. Reports log behavior metrics and the reward components separately. Do not expect the unverified 14–26 billion-step Discord result on this laptop in a few hours. Billions of learning transitions may take days or weeks depending on measured end-to-end rate, and architecture alone cannot guarantee strength. At 10,000 actual new learning transitions/s, one billion takes about 27.8 hours.

## W&B, checkpoints, safety of old work

If the selected environment has `wandb`, training reuses its saved SDK login or `WANDB_API_KEY`; it never displays or searches for keys. Project: **attentionforge**. Without a saved login it uses offline mode; without the package, local training/reports still work. Optional install in the selected environment: `"path\to\python.exe" -m pip install wandb`. To disable it, change `wandb.enabled` before creating a new run. Do not change an existing run's config silently.

A checkpoint contains actor, critic, optimizer, counters, config and Python/NumPy/Torch RNG states. Writes use a writable temporary file, fsync and atomic replacement. Native episodes restart on resume; it is a model/optimizer resume, **not bit-identical continuation of Bullet internal state**. The same model and RNG are restored, with a deterministic new native arena seed derived from the update. Worker scheduling does not change an arena's simulation RNG. Cross-platform bit-identical trajectories are not claimed.

`config.json` is copied into the run and must match on resume. Use a new name/config for experiments, for example `_RUN.bat train --run attention02 --config experiment02.json`. Existing RocketHive/GigaForge/NovaForge models and runs are never imported, overwritten or started. This project rotates only its own eight historical snapshots; it keeps the pinned baseline and current full checkpoint.

Use PAUSE while gaming. If the laptop becomes hot or unresponsive, reduce `n_envs`/`native_threads` in a **new experiment config**, rather than adding other simultaneous trainers. No automatic overclocking, power-plan changes or thermal guarantees.

## Export

**EXPORT.bat** creates a new `exports\attention01_<transition_count>` with **TorchScript `actor.pt` + RLBot v4 `bot.cfg`**, a shared observation encoder and an Octane appearance. It verifies reload logit/action agreement before reporting success. Run its `INSTALL.bat` and add `bot.cfg` in RLBot v4; local Rocket League launch still needs testing on your PC. The wrapper uses the same public features and one-tick decision delay, assuming normal 120Hz packet delivery. A different packet rate can introduce timing error.

**RLBot v5 `.toml` + `.lt` export is not implemented in this first version.** Attention models are not compatible with the old GigaLearn MLP `.lt` loader. Renaming `.pt` to `.lt` would not convert one. Training, native watch and reports work independently of RLBot.

## Source and reproducible build

Native RocketSim source: `ZealanL/RocketSim` at `c2baacb8f4b441dd8505e63c2aeb5a1679b60b02` (MIT). Source archive SHA256: `024f22ca36d6328331480e0e45bdc51ba52a4aee82560d1a17898a7ffa8fb28c`. Sources and upstream licenses are included. `tools/fetch_rocketsim.py` can restore this exact source. Pybind11: 2.13.6. The Windows module is built for CPython 3.11 x64 and needs the normal Microsoft C++ runtime; Python/Torch installations generally supply it. No LibTorch/CUDA DLLs are bundled or downloaded by the native module.

Build with a C++20 compiler, CMake and pybind11:

```bat
python -m pip install pybind11==2.13.6 cmake
python tools/fetch_rocketsim.py
python -m pybind11 --cmakedir
rem Pass the printed path as -Dpybind11_DIR=<path>:
cmake -S . -B build -A x64 -Dpybind11_DIR=<path>
cmake --build build --config Release --parallel 4
copy build\Release\_attention_native*.pyd attentionforge\
```

Development tests require pytest and local collision meshes: `python -m pytest -q tests`. `VALIDATION.json` records what was actually tested for this release. A successful smoke test is not a trained strong bot, and no trained weights from our short test are installed as your fresh bot.
