GigaLearn Research Hub: Defense Fundamentals 1v1 preset patch

INSTALL
1) Exit Research Hub completely. Make sure no C++ training is running.
2) Extract this zip into E:\Downloads\Chat_GPT_AI (preserve folder structure).
3) Double-click GigaLearn_Project\Research_Hub\ADD_DEFENSE_1V1.bat.
4) Restart Research Hub. Choose "Defense Fundamentals 1v1" in Experiments.
5) Use a unique experiment name such as defense_1v1_v1.
6) Optional seed checkpoint: use the EXACT numeric checkpoint directory under
   GigaLearn_Project\Research_Hub\experiments\smoke_balanced_01\checkpoints\2398176
   only if that folder exists and holds all seven GigaLearn checkpoint files.
7) Click Create experiment, Start selected. Verify the log says it LOADED the checkpoint,
   mode=defense teams=1v1, and starts increasing timesteps.
8) Train briefly, Request safe save + stop. Check a numeric checkpoint exists.

WHY NO REBUILD?
The existing patched C++ binary already understands GL_HUB_MODE=defense for any supported team count.
Only the Python GUI preset dictionary lacks a 1v1 choice. This patch adds that mapping.

SAFETY
- Script makes a timestamped backup of hub_core.py before replacing the file.
- Refuses unknown/different preset layouts; no partial source modifications.
- Idempotent: running twice is harmless.
- Does not touch .lt/.pt checkpoints, C++ source, existing experiments or datasets.
- Training against 1v1 GigaLearn opponents is NOT Nexto training.
- This is experimental reward shaping, not a verified competitive improvement.
