# NovaForge v1.2 download

[Download the ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.2.zip)

Adds train-until-paused mode and optional Weights & Biases status. Includes the Windows checkpoint-save fix and mixed-bot training with Nexto, Ripple, Chronos and GalactusV2 ports plus self-play. Extract into Chat_GPT_AI, replace NovaForge source files, and keep the existing .venv/assets/data. Existing install: run 17_WANDB_SETUP.bat once, then 18_START_OR_RESUME_WANDB.bat for continuous mixed-bot training. Launcher 15 pauses, 16 shows status and the dashboard URL. Fresh installs first complete the teacher/BC steps 10 through 12. Fresh installs start with 0_INSTALL.bat. Windows defaults: Python 3.11 x64, CPU, two workers. No competitive pretrained student is bundled.

[W&B and continuous training](NovaForge/WANDB_AND_CONTINUOUS.md) · [Mixed-bot guide](NovaForge/MULTI_BOT_GUIDE.md) · [Full guide](NovaForge/START_HERE.md) · [Plan](NovaForge/PLAN.md) · [Validation](NovaForge/VALIDATION.md) · [Bot research](NovaForge/BOT_RESEARCH.md)

This branch adds an isolated new project; the existing main branch and original training files are unchanged.
