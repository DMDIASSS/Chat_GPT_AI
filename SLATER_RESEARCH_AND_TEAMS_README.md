# Export audit, current-model checks and isolated team experiments

This update adds new tools and documentation. It does not replace the existing update180 continuation trainer or native backend. It contains no model weights, replays, raw Discord exports, searchable private text or source inventories. Extract into `E:\Downloads\Chat_GPT_AI`.

Read `docs/DISCORD_RESEARCH_FINDINGS.md` for the full supplied-export scan (73 HTML paths, 577,620 distinct messages), useful links, contextual evidence and coverage limits. `docs/FRAMEWORK_RESEARCH.md` reviews pinned public source; `docs/ATTENTION_NATIVE_COMPATIBILITY.md` records an actual C++ forward/gradient test. No one was contacted. All working files are in the cloud; access to the Windows PC was not established.

## Your completed continuation

The uploaded reports retain update180's initial actor after three unsuccessful cycles. This is no confirmed improvement, not proof all candidates degraded. Update40 tied the baseline's goal difference on 48 independent confirmation games (+10 each); update20 was worse in its screen, and update60's modest overall screen gain came with a Nexto-specific regression. See `docs/UPDATE180_CONTINUE02_RESULTS.md`. The plateau stops further training under that protocol; starting launcher20 again does not add more cycles after the plateau.

## First: inspect candidates and team contracts

`SLATER_21_CHECK_CURRENT_MODEL.bat` reads the completed trained candidate from `update180_continue02/progress.json`, takes verified private snapshots, and compares it with the protected original source in all nine 1–3-car formats, both colors, against Nexto and the source. It chooses `candidate`, not the latest rollback/resume file. By default that is update60 in the uploaded run. It uses one seed and 15-second games: 36 paired cases/72 games, exploratory only. Frozen teammates are identical for candidate and reference. The learner has learned kickoff; supporting teammates/rivals have scripted kickoff. CPU contention can slow other running training.

To check the promising update40 explicitly:

```bat
.venv\Scripts\python.exe -u slater_team_campaign.py check --candidate "data/isolated/versatile/update180_continue02/update_000040.pt"
```

For a separate scripted-learner check add `--scripted-student`. Increase `--seeds 4 --seconds 30` only for promising finalists, then use longer fresh-seed confirmation and retained 1v1/mechanics checks before selecting a playing replacement. A short all-format score is not a best-model guarantee.

Output: `data\isolated\team_campaigns\check_*\comparison.json` and `SHORTLIST.md`. The report breaks down formats and rivals, goals/concessions, team/learner touches and independent seed clusters. A goal from a frozen teammate is not proof the learner scored it. All formats are relative to the learner's team.

For a pure observation/controller audit without training:

```bat
.venv\Scripts\python.exe -u slater_team_eval.py audit
```

## Second: establish the native path without discarding knowledge

Run `SLATER_22_ATTENTION_NATIVE_PROBE.bat`. It tests your actual local update180, privately exports it, builds a separate CPU LibTorch probe, checks Python/C++ output parity and confirms actor gradients with a frozen teacher. It does not rebuild or change the GigaLearn backend. Existing Visual Studio tools, CMake/Ninja and matching Torch/CUDA development prerequisites are needed on Windows. Details and remaining migration work are in the compatibility document.

Cloud proved exact C++ logits, finite gradients in all44 tensors and a changed temporary student with an unchanged teacher. That is architecture feasibility, not a full native attention trainer or a speed/strength claim. No silent original-Nexto fallback is used by the local launcher.

## Optional: finite mixed-team continuation

After reviewing checks, pause other training to avoid competing processes and run `SLATER_23_TEAM_EXPERIMENT.bat`. This starts a separate `update180_teams01` from the protected update180 actor, not from a weak native MLP. Frozen teacher/teammates/rivals remain independent. Across updates it rotates all nine roster formats and match, ground, defense, recovery and low-boost starts. The actor is inherited exactly; critic/optimizers start fresh. PPO drift target0.005, anchor0.10 and LR3e-6 remain conservative experimental settings.

It runs40 updates, saves every update, and checks after20/40 on all formats. It never replaces the playing reference automatically. Human replay gradients are OFF. This is a controlled team exposure experiment, not coordinated full-squad PPO or an unlimited overnight promise. Total sampled budget is40,960 learner decisions; it is deliberately finite and may be insufficient to improve a capable actor. Reports separate physics ticks/s from useful learner decisions/s and collection/optimization time. Simulator correctness alone does not establish improvement.

`SLATER_23_PAUSE.bat` pauses at an update/evaluation boundary; wait for `TEAM_PAUSED`. Re-running the start resumes the saved checkpoint/settings. `SLATER_23_STATUS.bat` shows progress. Reports and preserved models are under `data\isolated\team_campaigns\update180_teams01`. `SHORTLIST.md` lists all checked candidates. Use a new run for changed code/settings; do not modify a saved protocol.

The recommended development priority is native attention collection/PPO with exact observation/timing parity, followed by apples-to-apples strength/hour benchmarks. `rlgym-learn` provides a useful Rust/shared-memory alternative while retaining PyTorch actors; Virx's Rust Nexto implementation is a reference requiring conversion/integration. There is no reason to replace the strong actor with a random policy to chase a throughput number.
