# NovaForge v1.12.0 / TriadBot v1.5.0: adaptive training opponents

[Download both project folders](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-adaptive-opponents-v1.12.0.zip)

Adds optional concession-per-minute opponent sampling to the existing selector06. Smoothed recent rates focus training on opponents that cause concessions, with 5–30% probability bounds, gradual updates and a retained base mix. State persists in the PPO checkpoint; W&B and reports show probabilities and estimated rates. Balanced W/D/L, rewards, frozen experts and champion protection are unchanged. This is a training experiment, not a demonstrated strength gain.

Pause selector06 with 28 and wait for saving; stop watch consoles. Copy chat_gpt_ai/novaforge and chat_gpt_ai/triadbot into your existing Chat_GPT_AI, replacing program files. Preserve .venv/assets/runs/exports. Run triadbot/33_ENABLE_HARD_OPPONENTS.bat, then 27 to resume your current model. No recreation or dependency reinstall. After a saved segment, pause and run 32 to share the updated report. Launcher 34 restores base sampling on the next resume.

Future guard reports retain per-opponent W/D/L and complete trials. Earlier aggregate-only reports cannot identify which opponent caused the concessions.

[Full sampling rules, resume and reporting](NovaForge/ADAPTIVE_OPPONENTS_v1.12.md) · [Six-expert setup](NovaForge/OCTANE_SIX_v1.11.md) · [Validation](NovaForge/VALIDATION.md)

Source ZIPs contain no weights, user reports or keys. Existing frozen-teacher/1v1 adapter limits still apply. Published on codex/novaforge-v1; main is unchanged.

Individual ZIPs: [NovaForge v1.12.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.12.0.zip) and [TriadBot v1.5.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.5.0.zip).
