# NovaForge v1.13.0 / TriadBot v1.6.0: unattended selector training

[Download both project folders](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-unattended-v1.13.0.zip)

Pause existing training with 28 and wait for saving. Copy the ZIP's chat_gpt_ai/novaforge and chat_gpt_ai/triadbot into the existing Chat_GPT_AI, replacing program files; preserve .venv/assets/runs/exports. No dependency reinstall or model reset. Open triadbot/35_LEAVE_RUNNING.bat and leave its console open. Stop with 28 or Ctrl+C.

35 backs up and resumes one continuous selector06 session. It configures adaptive opponents if not previously configured, respects an explicit disabled preference, keeps balanced W/D/L and regression stops, writes reports automatically, and exports each distinct retained champion. Fusion stays a frozen expert; no second training job or viewer starts. Files are under triadbot/reports and triadbot/exports; latest paths are in runs/selector06/autopilot.json.

Frozen expert inference is compiled in float32; unused two-tick observations are skipped; Fusion hash verification and evaluation model loading are cached with reset/invalidation checks. PPO settings, rewards, input timing and checkpoints remain compatible. A cloud environment benchmark measured about 18% higher decision throughput, not 10x–100x. This is not a user-laptop or learning-strength benchmark. Launcher 36 measures local environment speed while paused. A full native GigaLearn backend is not included.

[Unattended instructions, speed evidence and native-backend scope](NovaForge/UNATTENDED_v1.13.md) · [Measured samples](NovaForge/PERFORMANCE_v1.13.json) · [Validation](NovaForge/VALIDATION.md)

Source only: no model weights, private reports or keys. Existing 1v1/model-adapter limitations remain. Published on codex/novaforge-v1; main is unchanged.

Individual ZIPs: [NovaForge v1.13.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.13.0.zip) and [TriadBot v1.6.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.6.0.zip).
