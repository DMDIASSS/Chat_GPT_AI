# SLATER v0.4.1 — Overnight Evolutionary 1v1 PPO League

**Experimental / isolated. Not a guaranteed improvement or a verified champion.**

## What it does

One PPO student evolves from the uploaded v0.4.0 **u70** checkpoint. A generation creates:

- 1 larger RMS-relative Gaussian parameter perturbation of the incumbent;
- 2 smaller descendants of the large branch;
- 2 smaller perturbations of the incumbent;
- 1 smaller perturbation of a previous successful leader (when available).

Each trial then gets independent, short PPO fine-tuning, **without a scripted kickoff on the student**. Every frozen opponent gets the standard 168-physics-tick scripted Nexto kickoff when the approximate simulator kickoff predicate is active. Afterward the opponent switches to its actual 90-action neural policy. This is an approximation of stock RLBot kickoff timing, not identical live-game physics.

Training pool: stock Nexto, Cycle 9, Wavedash, OG Champion, V70, V60, plus the current provisional leader. Opponents are rotated after every completed episode with a seeded initial offset; opponent exposure is not exactly equal in wall-clock time because episode lengths vary. Each candidate is **screened independently** against six frozen, SHA-pinned opponents, both sides, matched seeds, and receives a second fresh-seed holdout if promising. The previous leader is kept if nobody passes. Checkpoints failing the screen are excluded from promotion, and disposable branch checkpoints may be deleted after an entire generation. The last ten successful previous leaders remain archived. No user-provided models or original champion files are deleted.

**Important:** Small branches mutate neural-network parameters by `1.2% * tensor RMS`, and larger branches by `6.5% * tensor RMS`, with a 3σ truncation. These are parameter perturbations, **not** guarantees of 1.2% or 6.5% behavior/skill changes; large branches do **not** invent new model architectures. PPO uses the existing v0.4.0 environment's reward (`0.20*ball_progress + 0.07*closing_distance + 0.35*student_touches - 0.002 + 10*goal_outcome`, with clipped components) and correct timeout bootstrapping. A frozen SHA-verified V60 teacher constrains policy drift at different strengths (`teacher_weight_small=0.30`, `teacher_weight_large=0.10`). Both PPO learning rate and optimizer state are stored in **full** checkpoint files; RLBot export `nexto-model.pt` is used for frozen opponents only.

### Installation

1. Unzip **directly into** `E:\Downloads\Chat_GPT_AI` alongside `slater_v040_multirival.py`, `slater_nexto_kickoff_v037a.py`, `slater_cycle9_native_ppo_v025.py`, `afk_team_research.py`, `.venv`, and existing `data/` files. Do not replace existing model files. This ZIP contains only scripts and docs.
2. Ensure `data\isolated\v040_multirival_campaign01_u0070.pt` is present (the full PPO source; merely an exported `nexto-model.pt` is **not** enough to resume PPO).
3. Find all six **actual** frozen-opponent model paths. If export folder names match `Nexto`, `Cycle9`, `Wavedash`, `Original Champion`/`OGChampion`, `V70`, `V60`, auto-discovery works. `wavedash` is explicitly set to `data/rlbot_exports/wavedash/nexto-model.pt`. To search in CMD use `dir /s /b data\rlbot_exports\nexto-model.pt`. If any is missed, set **that exact relative path** in `slater_v041_config.json` under `opponents`. The preflight lists candidates and **fails closed**, rather than silently substituting a different model.
4. All six frozen models **must** accept legacy Nexto obs `(1,1,32)`, `(1,37,24)`, `(1,37)` and output finite logits `(1,90)`. Python automatically loads both TorchScript exports and full Slater PPO checkpoints, but will reject incompatible networks or accidental duplicates.

### TEST FIRST — mandatory (no training)

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v041_tests -q
.venv\Scripts\python.exe slater_v041_overnight.py preflight
```

Expected: `23 passed` and `V041_PREFLIGHT_PASS`. The second command may fail when a specified export is missing or misidentified: **fix only the corresponding path**, don't bypass preflight or change pinned original data.

### REAL WINDOWS SMOKE — mandatory (makes a temporary candidate)

```bat
.venv\Scripts\python.exe -u slater_v041_overnight.py smoke
```

Expected `V041_SMOKE_PASS`. This performs one real RocketSim PPO update plus 2-sided evaluation against all **six** frozen opponents. On failure, open the paths printed under `data/isolated/v041_overnight/overnight01/smoke/.../training.log` and `evaluation.log`. **DO NOT** leave the unattended trainer running before the smoke test passes. The author environment cannot execute Windows RLGym/RocketSim end-to-end.

### OVERNIGHT UNLIMITED TRAINING — only after the smoke passes

```bat
.venv\Scripts\python.exe -u slater_v041_overnight.py start
```

Or double-click `SLATER_V041_START.bat`. `limit_generations: 0` means the program loops until you pause it, a safety check fails, or power/process shuts down. It does **not** guarantee perpetual skill improvement. One generation is several separate PPO trials and multi-opponent evaluations, so it may take a substantial time.

### Pause / resume / status

Pause from a second terminal (or `SLATER_V041_PAUSE.bat`):

```bat
.venv\Scripts\python.exe slater_v041_overnight.py pause
```

Pausing takes effect at the **end of the current trial or evaluation subprocess**, not instantly. Do not manually kill power to pause if avoidable. After crash/reboot, start from the last saved completed PPO update:

```bat
.venv\Scripts\python.exe -u slater_v041_overnight.py resume
```

Check status (or `SLATER_V041_STATUS.bat`):

```bat
.venv\Scripts\python.exe slater_v041_overnight.py status
```

**Crash safety:** Checkpoints use temporary files, `fsync`, then atomic `os.replace` on the same disk. One **completed PPO update** is saved as a full `.pt` before its report. If power dies during the current update, only that unsaved update is lost; the next `resume` recovers the newest validated checkpoint and reconstructs a missing JSON report if needed. Environment RNG and in-progress rollout buffers are **not** restored byte-for-byte; resume is approximate, not exact replay. Shutting down Windows terminates training; you must relaunch `resume` after power returns (this package does not install a Windows startup task).

### Paths and safety

All new checkpoints, logs, manifest, and state stay in:

`data\isolated\v041_overnight\overnight01\`

Most useful files:
- `league_state.json` — current **provisional** leader, generation, archived previous leaders and decisions.
- `leader.json` — simplified current provisional leader.
- `opponents_manifest.json` — absolute paths and SHA256 hashes of all six frozen opponents, locked on resume.
- `trials\g00001_*\training.log` — child PPO output and saved checkpoints.
- `evaluations\g00001\*_screen.json` / `*_holdout.json` — paired comparisons, timeouts separately labeled.
- `pause.request` — created by pause, cleared by `resume`.

Protected user checkpoints, original `data/autoleague/champion.pt`, `data/afk_improved/best_verified.pt`, Cycle9, V60, V70 source, and existing RLBot exports are never overwritten. The previous **AFK best-verified is believed to be Cycle 9** but must not be confused with the evolving simulator-only provisional leader. **u70 is the selected initial provisional leader based on very small first-goal tests, not an established full-match champion**. Run independent full-length real RLBot matches to establish actual strongest.

### Scoring math

Each evaluation episode produces 1 if the student scores first, -1 if it concedes first, 0 if the horizon expires. This **zero is censored**, NOT a draw or a win. For identical `(seed,side,opponent)` conditions, calculate `delta = candidate_outcome - leader_outcome` (range -2..+2); rank by mean delta. Every fixed opponent has equal episode count, so simple mean provides equal opponent weight. Initial screen: `1 seed × 2 sides × 6 = 12 paired evaluations`. A top finalist then receives **fresh independent** holdout seeds: `3 seeds × 2 sides × 6 = 36 paired evaluations`, resulting in **72 simulated episodes** (both policies). Promotion requires at least ten resolved pairs, mean delta >= `0.13`, and no core opponent's mean delta worse than `-0.34`. This is a **heuristic**, not a statistically proven confidence bound; small samples can select spurious winners, so promotions are marked `PROVISIONAL_NOT_LIVE_RLBOT_VERIFIED`. For better confidence, increase `screen_seeds`/`promotion_seeds` and `eval_steps` in a **NEW run name before first starting**; do **not** edit config mid-run.

At most 6 candidates compete in each generation; 5 in generation 1. A large mutation generates two local derivatives from its **trained result**, and small incumbent branches give stability. A previous-leader branch allows recovery from a local optimum. No model is automatically promoted into the original AutoLeague `champion.pt`, AFK `best_verified.pt`, or RLBot export folders.

### Speed and hardware

Prior Windows preflight measured ~330 decisions/sec for an old scripted opponent and ~266 decisions/sec for tick-aware stock opponent; both **exclude PPO optimization and evaluation**, and not all matches use the same physics path. No GPU training is assumed; the Nexto TorchScript model may contain fixed CPU tensors. These measurements don't imply millions of decisions overnight. Disable Windows automatic sleep for the session; monitor CPU temperature, fan and free disk. Keep at least 2 GiB disk space.

### Replays / parsing (separate future work)

A `.replay` records estimated/sampled game state, not complete exact controller button presses. A parser reconstructs structured car/ball trajectories. Inverse dynamics estimates controls; `VirxEC/replay-to-rocketsim` provides relevant reconstruction tools: https://github.com/VirxEC/replay-to-rocketsim. Replay->RocketSim demonstration parity and quality must pass dedicated tests **before imitation learning**. This version deliberately does not feed unverified professional replay or TAS labels into the protected PPO policy.

### Exit reasons

- Missing, incompatible, duplicated or modified opponents: **stop before training**.
- Missing u70 full checkpoint, wrong hashes, or insufficient space: **stop**.
- Existing overnight process owns Windows file lock: **stop**.
- Some branches fail: error saved in `failure.json`, other valid branches may continue.
- All branches fail or all evaluation results fail: **stop safely** with diagnostics, rather than pretending success.
- No candidate clears the independent holdout: retain incumbent leader and try new generation.

**Important:** This is a tested script release with offline unit tests, **not** an assertion that an unattended Windows overnight run has already succeeded. Use the real smoke command first.
