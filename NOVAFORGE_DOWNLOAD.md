# Research tools: NovaForge v1.9.0 / TriadBot v1.2.0

[Download the combined source update ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-research-v1.9.0.zip)

Adds versioned bounded objectives, isolated experiment forks, immutable configuration/source records, separate development/validation/test seed banks, complete evaluation checkpoint archives, per-session CSV retention and expert-use measurements. Default rewards and expert weights retain their existing values. This is the foundation for controlled reward experiments; no stronger model or optimal reward is claimed.

Pause selector training with 8 and wait for saving to finish. Inside the ZIP's chat_gpt_ai folder, copy novaforge and triadbot into the existing Chat_GPT_AI folder and replace program files. Keep .venv/assets/runs/exports. No reinstall or reset is needed. In triadbot, run 10_BACKUP_SELECTOR.bat, then 11_VALIDATE_SELECTOR.bat (64 games total), then 12_RESEARCH_REPORT.bat. The report ZIP contains no weights or raw logs.

[Detailed staged plan, results and experiment commands](NovaForge/RESEARCH_v1.9.md) · [Triad launchers](TriadBot/README.md) · [Validation](NovaForge/VALIDATION.md)

Individual source packages:

- [NovaForge v1.9.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.9.0.zip)
- [TriadBot v1.2.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.2.0.zip)

[Training and model exports](NovaForge/FINISH_AND_FUSION.md) · [Attribution](NovaForge/THIRD_PARTY.md)

Source packages contain no model weights or user run data. Published on codex/novaforge-v1; main remains unchanged. Reward search and automatic reward adjustment are staged follow-ups, not implemented claims in this release.
