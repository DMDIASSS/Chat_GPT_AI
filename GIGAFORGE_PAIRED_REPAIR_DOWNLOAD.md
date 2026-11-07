# Paired evaluation repair and training-focus update

[Update ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Paired-Eval-Training-Focus-Update.zip) | [Complete project ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Paired-Eval-Windows.zip)

Existing research02: run 4_PAUSE and wait for the console to finish. Merge chat_gpt_ai into the existing Chat_GPT_AI folder, including gigaforge/native. Keep runs, models, environments and exports. Run 9_VERIFY, then 3_START_OR_RESUME. This resumes existing optimizer checkpoints and automatically records a training-focus policy when the measured run is spending too much on evaluation without accepted gains. No CUDA download or local compiler is required. A fresh installation needs 1_SETUP_GPU or 0_SETUP_CPU before verification, and 17 starts research02.

The native repair gives each evaluation arena its own random-engine state and orders car updates by stable car IDs, fixing thread-dependent respawns and pointer-dependent update order. The before/after Linux check changed from five unequal identical-model comparisons out of 64 to zero; the Windows full-length check also passed. For the uploaded stalled study, training focus changes full blocks from 65,536 to 262,144 decisions and branch caps from 524,288 to 2,097,152, concentrating on control and the best measured alternative with regular exploration. Reward formulas, original actors/hitboxes, epochs and promotion requirements are preserved. W&B status now refreshes completed progress.

[Detailed behavior](GigaForge/PAIRED_REPAIR.md) | [Release validation and hashes](research/GigaForge-paired-eval-release.json)

No stronger policy is bundled or claimed. The report had no confirmed improvement after 30 trials and six confirmations. These fixes improve measurement and learning allocation; a longer run must establish playing-strength gains. Send 8_REPORT after another hour.
