# Native trainer source preview and Chronos body correction

[Download ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-native-preview.zip)

Contains chat_gpt_ai/novaforge, triadbot, forgeleague and gigaforge. Pause trainers and merge program files into the existing chat_gpt_ai folder, preserving models, runs and environments. Chronos uses Breakout and Galactus uses Octane. Existing Octane ForgeLeague runs are preserved and automatically forked into a separate Breakout experiment for training/watch/export.

GigaForge is a compiled-and-tested Linux CPU source preview. A verified Windows executable is not included; Windows build validation is running in Actions. The GPU path is not yet hardware-validated. Do not leave this preview training unattended on Windows. Read GigaForge/README.md for build, verification, objective, benchmark and launch instructions.

Linux: 28 actual feature/mask/network comparisons passed; actual native warmup, actor updates, optimizer resume and cross-bot paired WDL passed for both families. Existing Python suite: 174 passed, 28 optional skipped. These are correctness checks, not proof of stronger play or a laptop SPS claim. No user weights, reports or keys are published.
