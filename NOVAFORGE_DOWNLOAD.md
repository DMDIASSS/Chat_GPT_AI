# NovaForge v1.3 download

[Download the ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.3.zip)

Adds one-click progress reports, offline charts and an earliest/current checkpoint comparison. Preserves PPO CSV history across resume. Includes continuous W&B training, the Windows checkpoint-save fix, and mixed-bot training with Nexto, Ripple, Chronos and GalactusV2 ports plus self-play. Pause with launcher 15 before updating, extract into Chat_GPT_AI and replace NovaForge source files while keeping .venv/assets/data/models/runs. Run 1_CHECK.bat, then 19_EXPORT_PROGRESS_REPORT.bat and upload its small report ZIP in the chat. For a paired checkpoint evaluation, pause with 15 and run 20_COMPARE_PROGRESS.bat. Resume training with 18. Fresh installations start with 0_INSTALL.bat and the teacher/BC steps 10–12; W&B setup is 17. Windows defaults: Python 3.11 x64, CPU, two workers. No competitive pretrained student is bundled.

[Progress reports, comparisons and SPS](NovaForge/PROGRESS_REPORTS.md) · [Technical archive findings](NovaForge/ARCHIVE_RESEARCH.md)

[W&B and continuous training](NovaForge/WANDB_AND_CONTINUOUS.md) · [Mixed-bot guide](NovaForge/MULTI_BOT_GUIDE.md) · [Full guide](NovaForge/START_HERE.md) · [Plan](NovaForge/PLAN.md) · [Validation](NovaForge/VALIDATION.md) · [Bot research](NovaForge/BOT_RESEARCH.md)

This branch adds an isolated new project; the existing main branch and original training files are unchanged.
