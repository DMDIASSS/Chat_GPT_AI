# SLATER v0.4.1 — Overnight Evolutionary 1v1 PPO League

**Experimental / isolated. Not a guaranteed improvement or a verified champion.**

## What it does

One PPO student evolves from the local v0.4.0 **u70** checkpoint. The updated generation creates:

- 1 ordinary PPO continuation with no parameter perturbation, retaining Adam state;
- 1 larger RMS-relative Gaussian parameter perturbation of the incumbent;
- 1 smaller descendant of the large branch;
- 2 smaller perturbations of the incumbent;
- 1 smaller perturbation of a previous successful leader (when available).

Each trial then gets independent, short PPO fine-tuning, **without a scripted kickoff on the student**. Every frozen opponent gets the standard 168-physics-tick scripted Nexto kickoff when the approximate simulator kickoff predicate is active. Afterward the opponent switches to its actual 90-action neural policy. This is an approximation of stock RLBot kickoff timing, not identical live-game physics. The new run enables RLGym's one-tick RLBot action delay for both training and evaluation.

`training_reset: "mixed_ground"` uses the existing `fundamentals` curriculum: 50% kickoff, 35% randomized ground starts, 15% defense starts, sampled independently at reset. This broadens the states PPO sees beyond kickoff play. Evaluation remains kickoff-only, so the paired comparison protocol is retained. Set `training_reset: "kickoff"` in a **new run** for a controlled ablation. These starts are synthetic, not reconstructed professional replay demonstrations.

Optional `replay_starts` can replace a configured fraction of resets with prepared, validated 1v1 ReplayFrame states. It defaults to null and needs `requirements-slater-replays.txt` only when used. Dataset contents are SHA-locked. See [SSL training next steps](docs/SSL_TRAINING_NEXT_STEPS.md) for format, setup and the review of the supplied upstream projects, including the successful replay-pretraining/Ripple research direction.

`target_kl: 0.02` bounds the mean exact `KL(old rollout policy || updated policy)` on the collected states. After each epoch, an excessive update is rolled back together with its Adam moments; earlier accepted epochs remain. The critic can retain its supervised updates. The protected V60 teacher KL penalty is separate. Logs report accepted epochs, policy KL and rollback; this limit does not bound behavior in all unseen states or parameter mutations before training.

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

All tests must pass, followed by `V041_PREFLIGHT_PASS`. The suite includes real RocketSim reset checks when that dependency is installed. The second command may fail when a specified export is missing or misidentified: **fix only the corresponding path**, don't bypass preflight or change pinned original data.

The default run is now `overnight02`; keep previous `overnight01` results. Back up your existing config before replacing it, preserve your six opponent paths, and use a new run name for these changes. Existing league configuration hashes intentionally refuse changed settings on resume.

### Integration check without private checkpoint files

When only original Nexto is available, this additional check exercises real simulator collection, a bounded PPO update, timeout bootstrapping and four paired evaluation cases. It writes only a JSON report and discards the temporary trained actor:

```bat
.venv\Scripts\python.exe slater_v041_validate.py --steps 512 --out data/isolated/v041_integration01.json
```

Expected `V041_INTEGRATION_PASS`. Use a new filename on repetition. This does **not** replace the full six-opponent preflight/smoke below, continue V70, or prove improved skill.

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

`data\isolated\v041_overnight\overnight02\`

Most useful files:
- `league_state.json` — current **provisional** leader, generation, archived previous leaders and decisions.
- `leader.json` — simplified current provisional leader.
- `opponents_manifest.json` — absolute paths and SHA256 hashes of all six frozen opponents, locked on resume.
- `trials\g00001_*\training.log` — child PPO output and saved checkpoints.
- `evaluations\g00001\*_screen.json` / `*_holdout.json` — paired comparisons, timeouts separately labeled.
- `pause.request` — created by pause, cleared by `resume`.

Protected user checkpoints, original `data/autoleague/champion.pt`, `data/afk_improved/best_verified.pt`, Cycle9, V60, V70 source, and existing RLBot exports are never overwritten. The previous **AFK best-verified is believed to be Cycle 9** but must not be confused with the evolving simulator-only provisional leader. **u70 is the selected initial provisional leader based on very small first-goal tests, not an established full-match champion**. Run independent full-length real RLBot matches to establish actual strongest.

### Scoring math

Each evaluation episode produces 1 if the student scores first, -1 if it concedes first, 0 if the horizon expires. This **zero is censored**, NOT a draw or a win. For identical `(seed,side,opponent)` conditions, calculate `delta = candidate_outcome - leader_outcome` (range -2..+2); rank by mean delta. Every fixed opponent has equal episode count, so simple mean provides equal opponent weight. Initial screen: `1 seed × 2 sides × 6 = 12 paired evaluations`.

The default finalist holdout now starts with **16 fresh seeds × 2 sides × 6 opponents = 192 pairs / 384 simulated episodes per finalist**. Seeds occupy disjoint screen/holdout ranges across generations. Cached reports must match model hashes, the opponent manifest, exact seeds, horizon and action-delay setting; selection recomputes its summary from raw pairs.

Promotion still requires mean delta >= `0.13`, at least `max(10, 2 * holdout seed count)` resolved pairs and no core opponent's mean delta worse than `-0.34`. It additionally requires complete six-opponent/two-side coverage, at least eight non-tied seed clusters, and an exact one-sided sign test across **seed averages**. The twelve correlated pairs from one seed supply one observation. Seed ties provide no positive evidence.

For generation `g`, each of at most two finalists receives `alpha = promotion_error_budget / (2 * g * (g + 1))`, with total configured budget `0.05`. This corrects for testing two finalists and repeated generations, assuming fresh independent seed samples and a fixed evaluation protocol. Holdout size grows slowly when needed so the tightening threshold remains attainable. The sign test measures consistency of positive seed-level differences; it is not a confidence bound on mean skill or a full-match win rate. More conservative selection costs more evaluation time and can reject small real gains.

Promotions remain `PROVISIONAL_NOT_LIVE_RLBOT_VERIFIED`. Increase `screen_seeds`, the minimum `promotion_seeds`, or `eval_steps` in a **NEW run before starting**; do **not** edit config mid-run. The finite evaluation seed namespace stops the runner before training if exhausted.

At most 6 candidates compete in each generation; 5 in generation 1. A large mutation generates one local derivative from its **trained result**, while the unperturbed PPO branch and small incumbent branches provide alternatives. A previous-leader branch allows recovery from a local optimum. No model is automatically promoted into the original AutoLeague `champion.pt`, AFK `best_verified.pt`, or RLBot export folders.

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

## Cloud validation and next competitive milestones

On 2026-10-12, the updated path ran on Linux CPU with original SHA-pinned Nexto: 512 rollout decisions, four completed training episodes, three timeout bootstraps, two accepted PPO epochs, and four paired evaluation cases. Rollout policy KL was `0.000832`, below `0.02`; actor parameters changed, frozen teacher parameters and original model bytes remained intact. This is integration evidence, not superiority or SSL evidence. The private six-opponent files and full V70 checkpoint are absent from this checkout; full league preflight correctly stops at missing Cycle9. Keep large artifacts out of Git, but provide these models separately in the machine that trains.

Next milestones for the SSL+ objective:

1. Run the updated full V70 smoke, then a bounded campaign. Compare kickoff-only versus mixed-ground training on a common independent evaluation set; record goals, censored outcomes and both team sides.
2. Extend evaluation to five-minute matches and ground/defense retention drills, then test exported candidates against stronger available opponents and skilled humans in offline/LAN RLBot matches. Nexto-only first-goal results do not establish SSL or professional-level play.
3. Scale collection after measuring complete PPO/evaluation throughput. Add replay-derived starting states before imitation labels; reconstructed controller inputs need their own fidelity tests.
4. Add aerial, recovery and team-play curricula with meaningful physical success measures, while retaining the incumbent's offense in independent tests. Keep the existing strongest checkpoint as a reference.

The supplied RLBot exports inform this ordering. The March 2026 FAQ lists stronger server-hosted bots and recommends the ML FAQ: https://wiki.rlbot.org/v5/botmaking/machine-learning-faq/. The January 2025 RLGym announcement documents the one-tick action-delay option. Early community messages describe using replay positions for reset scenarios and the absence of complete controller inputs; those are historical experience, not proof that modern replay learning is impossible. The April 2026 announcement recommends RLBot v5 for future distribution. These exports provide context; they do not grant access to hosted bot weights or establish our bot's rank.
