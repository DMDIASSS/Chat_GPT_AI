# NovaForge v1.4 download

[Download the ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.4.zip)

Adds continuous frozen-teacher copying, mild shared-return weighting, and LibTorch .lt + RLBot v5 .bot.toml export with the required Python adapter. All four teachers remain frozen. The student learns their executed controls through supervised updates, with separate validation rollouts and best-checkpoint selection. Original teacher reward functions are not recoverable from their weights; the shared simulator return provides a bounded preference for better demonstrated outcomes.

The ZIP contains chat_gpt_ai/novaforge. Extract into the parent of your existing project folder (for example E:\Downloads), merge/replace the source files, and retain .venv/assets/datasets/models/runs. Pause the old run with 15 first. Run 1_CHECK.bat, then 21_START_OR_RESUME_COPY.bat. Launcher 22 pauses copying, 23 shows status, 24 watches, 25 exports .lt + .bot.toml, 26 reports and 27 evaluates. Launcher 29 exports the old diverse01 bot; 28 packages a supported actor. Fresh installs start with 0_INSTALL.bat, download teachers with 3_FETCH_TRAINERS.bat and set up W&B with 17. No pretrained student or teacher weights are bundled.

[Frozen teacher copying](NovaForge/FROZEN_TEACHER_COPYING.md) · [.lt and v5 export](NovaForge/V5_EXPORT.md) · [Actor packager](NovaForge/PT_TO_TOML.md)

[Progress reports, comparisons and SPS](NovaForge/PROGRESS_REPORTS.md) · [Technical archive findings](NovaForge/ARCHIVE_RESEARCH.md)

[W&B and continuous training](NovaForge/WANDB_AND_CONTINUOUS.md) · [Mixed-bot guide](NovaForge/MULTI_BOT_GUIDE.md) · [Full guide](NovaForge/START_HERE.md) · [Plan](NovaForge/PLAN.md) · [Validation](NovaForge/VALIDATION.md) · [Bot research](NovaForge/BOT_RESEARCH.md)

This branch adds an isolated new project; the existing main branch and original training files are unchanged.
