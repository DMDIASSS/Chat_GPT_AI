# Evaluation hotfix: NovaForge v1.8.1 / TriadBot v1.1.1

[Download the combined evaluation-fix ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-eval-fix-v1.8.1.zip)

Fixes blank/slow manual selector evaluation: the missing one-thread Torch setting is applied before model loading, launcher 7 prints immediately and runs unbuffered, and every game has visible start/score output plus running progress about every five wall-clock seconds during play. Training-lock errors explain how to pause. Cancellation preserves weights and earlier complete results; completed reports identify the tested checkpoint.

Close the old evaluation console with Ctrl+C. Pause selector training with 8 and wait for it to finish saving. Inside the ZIP's chat_gpt_ai folder, copy novaforge and triadbot into the existing Chat_GPT_AI folder and replace program files. Keep .venv/assets/runs. Run 7_EVALUATE_SELECTOR.bat again. Its default is 32 games; allow all games to finish. Output: triadbot/runs/selector01/wdl.json. No reset, retraining or dependency reinstall is needed.

[Detailed hotfix and short pipeline check](NovaForge/EVALUATION_HOTFIX_v1.8.1.md) · [Triad selector/body guide](NovaForge/TRIAD_SELECTOR_v1.1.md) · [Validation](NovaForge/VALIDATION.md)

Individual source packages are also available:

- [NovaForge v1.8.1](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.8.1.zip)
- [TriadBot v1.1.1](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.1.1.zip)

[Main training and model exports](NovaForge/FINISH_AND_FUSION.md) · [Triad launchers](TriadBot/README.md) · [Attribution](NovaForge/THIRD_PARTY.md)

Source packages contain no model weights or user run data. Published on codex/novaforge-v1; main remains unchanged. The update changes evaluation execution/progress, not learned weights or match rules.
