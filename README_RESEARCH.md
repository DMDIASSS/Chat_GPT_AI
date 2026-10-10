# AFK Improved — Aggressive Research v1

**Purpose:** Explore big changes without destroying the strongest verified Cycle 9 checkpoint. CPU only for the current bundled Nexto TorchScript.

**First:** Finish any active `LEARN_ONE_CLICK.bat`, AFK Improved PPO, or ordinary AutoLeague job. Do not run multiple learning jobs simultaneously. Then run `RESEARCH_0_CHECK.bat`, followed by `RESEARCH_1_TRAIN_AND_COMPARE.bat`.

The runner trains **four separate one-cycle PPO variants**, each initialized from the immutable original Cycle 9. It uses actor learning rates `3e-6`, `1.2e-5`, `3e-5`, `8e-5` (higher rates are deliberately risky). It also adjusts PPO clipping, exploration entropy, and the anchor to the original. No branch can overwrite another branch's checkpoint. Run times depend on your CPU and are not promised.

The runner can also include the existing **AFK training cycle-9 candidate** if it finds exactly one matching file in `data/afk_improved/league/inconclusive/`. It then re-evaluates all completed candidates against original Nexto and untouched Cycle 9 on *common held-out 1v1 first-goal episodes*. No model automatically replaces `champion.pt`, `best_verified.pt`, or original Cycle 9. This is a **research experiment**; the provisional leader still needs a larger separate 1v1 benchmark and ideally five-minute matches before promotion.

## Controls

- `RESEARCH_0_CHECK.bat`: verify source hash and ensure other trainers are idle
- `RESEARCH_1_TRAIN_AND_COMPARE.bat`: train four variants; evaluate against baseline
- `RESEARCH_2_PAUSE.bat`: pause between whole independent experiments (or their evaluations), not during a PPO rollout
- `RESEARCH_3_RESUME.bat`: continue completed branches are skipped and cached evaluations reused
- `RESEARCH_4_STATUS.bat`: print JSON research status
- `RESEARCH_5_EVAL.bat`: re-run/finish withheld evaluations without training (already evaluated identical SHA/seed are skipped)

All files: `data/afk_improved/aggressive_research/` — each branch has its own full checkpoint history, logs, and audit file. Use `research_evaluations.json` for comparing models. You can archive this folder with `Compress-Archive` (exclude large `.pt` files when sharing reports).

## Safeguards and technical limitations

- Input weights are SHA256-verified (`50f34d4a3723...`). No source file writes.
- Main AutoLeague, existing AFK PPO and replay/TAS learning locks are checked before starting; one research runner may execute at a time.
- CPU only; the bundled TorchScript policy fails on CUDA because of a baked-in CPU tensor.
- Each branch is **trained in 1v1**, not 1v2 / 2v2 / 3v3. Multi-car observation/state parity must be solved separately.
- Some high learning rates may diverge. They do not affect verified models. In a failure, the branch is logged, and others continue.
- No automatic promotion, deletion, rollback of your working main lineage, or replay/TAS learning in this research tool.
- This uses the bundled project `auto_league.py`; if that file has been modified since your existing installation, run the preflight and short test first. RocketSim was **not** executable in the build environment.

**Already running LEARN_ONE_CLICK?** Do not start research or run `RESEARCH_5_EVAL.bat` until that job finishes. Research checks the replay learner OS lock and refuses overlapping jobs.
