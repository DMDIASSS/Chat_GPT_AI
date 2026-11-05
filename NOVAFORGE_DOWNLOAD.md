# NovaForge v1.6.0 download

[Download the ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.6.0.zip)

Starts the actual Chronos policy as a new reward-driven PPO learner. Four frozen opponents, snapshot self-play, frozen initialization KL, critic warmup, full optimizer resume, W&B, initial/current comparisons and v5/native-component exports are included. Existing copy02 stays in its own run folder.

Pause old training, merge chat_gpt_ai/novaforge at the project folder's parent, and run 1_CHECK.bat. Launcher 35 starts/resumes chronos01 until paused; 36 pauses, 37 shows status, 38 watches, 39 compares with initialization and creates a report, 40 exports .lt/.bot.toml, 41 reports and 42 watches initialization. Fresh installations first use 0_INSTALL.bat. After 32,768 learner decisions, pause, run 39 and send the report before a long run.

[Step-by-step Chronos training](NovaForge/CHRONOS_TRAINING.md) · [Upstream review](NovaForge/UPSTREAM_REVIEW.md) · [Detailed plan](NovaForge/PLAN.md) · [Validation](NovaForge/VALIDATION.md)

The upstream review inventories 233 public repositories across the five supplied accounts, retrieves 203 root READMEs and examines selected training/deployment source from 19 pinned archives. Native GigaLearn/Rust rollout integration, replay reconstruction and additional Byte-family adapters remain separate work, with explicit compatibility gates.

Fixes an orange-team reset modifying shared kickoff spawn arrays. Historical kickoff comparisons from affected versions were not reliably paired; new comparisons assert identical starting observations. Also retains the checked RLViser sender/camera build and safe Windows viewer diagnostics.

The ZIP contains chat_gpt_ai/novaforge. Keep existing .venv/assets/datasets/models/runs. No model weights are bundled; launchers download pinned, hash-verified originals. This package does not grant new rights over them. No playing-strength gain over original Chronos, Windows game-transfer result or native GigaLearn throughput is claimed.

[Original installation and replay workflow](NovaForge/START_HERE.md) · [Old copying workflow](NovaForge/FROZEN_TEACHER_COPYING.md) · [Viewer setup](NovaForge/RLVISER_CAMERA.md) · [Attribution](NovaForge/THIRD_PARTY.md)

The source is published on codex/novaforge-v1. The existing main branch and original project files are unchanged.
