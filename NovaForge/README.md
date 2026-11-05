# NovaForge v1.8.1

**Evaluation fix:** [thread limit, immediate launcher output and per-game progress](EVALUATION_HOTFIX_v1.8.1.md).

**TriadBot v1.1:** [learned options selector, exact model pins, fixed body settings and immediate local v5 exports](TRIAD_SELECTOR_v1.1.md). Existing Chronos runs and launchers remain available.

**Current guide: [Finish, unattended safeguards, fusion and both exports](FINISH_AND_FUSION.md).** Launcher 35 upgrades/resumes chronos01 with backed-up settings, longer reward credit, automatic W/D/L checks, protected champion and regression stops. Launcher 38 still watches the latest learner; 51 watches the champion. Launcher 40 exports both .pt/.cfg and .lt/.toml. Launcher 43 starts the separate fusion01 experiment. [TriadBot](SECOND_PROJECT.md) is a separate random three-expert project.

Continue training the actual Chronos policy with reward-driven PPO, four frozen opponents and snapshot self-play. The new **chronos01** run is separate from earlier copying experiments.

## Start

Pause copy02 with 22 and wait for its console to exit. Merge this ZIP at your project folder's parent; it contains **chat_gpt_ai/novaforge/**. Keep .venv, assets and runs. Run **1_CHECK.bat**, then **35_START_OR_RESUME_CHRONOS.bat**. Fresh installations first need **0_INSTALL.bat**.

| Launcher | Action |
| --- | --- |
| 35 | Start/resume Chronos PPO continuously with W&B |
| 36 | Request a safe training pause |
| 37 | Show training/dashboard status |
| 38 | Watch the latest learner with automatic RLViser camera |
| 39 | Compare current vs unchanged initialization; export a report |
| 40 | Export .lt components and an RLBot v5 .bot.toml launcher |
| 41 | Export a metrics report ZIP |
| 42 | Watch the unchanged Chronos initialization |

Unattended W/D/L checks run every 131,072 decisions. Use 41 to export a report when needed. Initializing from Chronos avoids learning basic controls from scratch; improvement over Chronos still needs gameplay evidence.

[Step-by-step Chronos guide](CHRONOS_TRAINING.md) · [Upstream review](UPSTREAM_REVIEW.md) · [Plan](PLAN.md) · [Validation](VALIDATION.md) · [Attribution](THIRD_PARTY.md)

## What changed

- Actual 225-feature / 90-action Chronos shared head and policy weights, preserving its mirror convention, action mask and delayed controls.
- Separate new critic, critic-only warmup, small actor learning rate and frozen initialization KL penalty.
- Frozen original Chronos, GalactusV2, Ripple and Nexto opponents, plus latest/historical frozen learner snapshots.
- Goal/concede reward and discount-consistent potential shaping; full optimizer resume, bounded checkpoint retention and W&B using the SDK's saved local login.
- Permanent initialization for paired screening, initial/current viewing, metrics reports, combined actor.lt and separate SHARED_HEAD.lt / POLICY.lt exports.
- Fixed shared kickoff spawn arrays being modified during orange-team resets. Historical kickoff comparisons from affected versions were not reliably paired and should not rank policies. New comparisons verify identical initial observations.

The review inventories 233 public repositories from the five supplied accounts, retrieves 203 root READMEs and examines selected training/deployment source in 19 pinned archives. It records compatibility limits and deferred integrations; no native GigaLearn throughput or strength gain is claimed.

## Existing experiments

Old runs and launchers remain available: [copy02](FROZEN_TEACHER_COPYING.md), [candidate inspection](CANDIDATE_REVIEW_v1.5.4.md), [mixed PPO](MULTI_BOT_GUIDE.md), [reports](PROGRESS_REPORTS.md), [W&B](WANDB_AND_CONTINUOUS.md), [general installation and replay workflow](START_HERE.md), [viewer setup](RLVISER_CAMERA.md), and [earlier export formats](V5_EXPORT.md).

Designed for Windows 10, i5-10300H, GTX 1650 Ti Mobile and 16 GB RAM. Defaults use two simulator workers. Actual laptop CUDA speed and full offline RLBot matches need user testing. The source ZIP contains no model weights; launchers fetch pinned, hash-verified originals. It does not grant new rights over those originals.
