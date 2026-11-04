# NovaForge v1.5 download

[Download the ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.5.zip)

Corrects a teacher-copying shortcut: transition windows are retained, previous-action inputs are disabled in the actor, and fresh copy02 training starts with first-contact demonstrations. Published models are selected using their own kickoff monitoring plus copying loss. All teachers stay frozen; shared simulator returns mildly weight supervised labels. The original teachers reward functions remain unknown.

The ZIP contains chat_gpt_ai/novaforge. Extract into the parent of your existing project folder (for example E:\Downloads), merge source files, and keep .venv/assets/datasets/models/runs. Pause the old copying process first. Run 1_CHECK.bat and then 21_START_OR_RESUME_COPY.bat for the fresh copy02. Launcher 22 pauses, 23 shows status, 24 automatically opens the learner camera, 25 exports .lt + .bot.toml, 26 reports, 27 evaluates against the named bots and 30 screens mechanics. Launcher 29 exports diverse01. No trained student or teacher weights are bundled.

Automatic viewing finds chat_gpt_ai\rlviser.exe. The requested 110 FOV / 270 distance / -4 pitch learner ballcam uses a checked camera build downloaded once; the original viewer is preserved. Launcher 31 optionally prepares it ahead of watching. The fresh student still needs training and gameplay validation.

[Copying correction](NovaForge/COPY_CORRECTION_v1.5.md) · [Automatic RLViser camera](NovaForge/RLVISER_CAMERA.md)

[Frozen teacher copying](NovaForge/FROZEN_TEACHER_COPYING.md) · [.lt and v5 export](NovaForge/V5_EXPORT.md) · [Actor packager](NovaForge/PT_TO_TOML.md)

[Progress reports, comparisons and SPS](NovaForge/PROGRESS_REPORTS.md) · [Technical archive findings](NovaForge/ARCHIVE_RESEARCH.md)

[W&B and continuous training](NovaForge/WANDB_AND_CONTINUOUS.md) · [Mixed-bot guide](NovaForge/MULTI_BOT_GUIDE.md) · [Full guide](NovaForge/START_HERE.md) · [Plan](NovaForge/PLAN.md) · [Validation](NovaForge/VALIDATION.md) · [Bot research](NovaForge/BOT_RESEARCH.md)

This branch adds an isolated new project; the existing main branch and original training files are unchanged.
