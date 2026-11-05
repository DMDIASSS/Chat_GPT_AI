# Selector diagnostics and watch fix: NovaForge v1.9.1 / TriadBot v1.2.1

[Download the combined source update ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-diagnostics-v1.9.1.zip)

Adds 13_DIAGNOSE_SELECTOR.bat: free-choice selector probabilities, fixed Chronos/GalactusV2/Ripple comparisons through the common adapter, and optional reference-body checks. The default Breakout run has 48 short games (30 simulated seconds each), then prints DIAGNOSTIC_REPORT_READY with a shareable ZIP. The diagnostic does not train, change checkpoint files or promote a champion. Launcher 12 also includes the most recent diagnostic.

Fixes Triad watch launchers 1 and 5: RLViser was prepared in novaforge while the native sender looked in the current triadbot folder. The watch wrapper now resolves selector paths before running from novaforge, restores the original directory on exit/error, and explains busy viewer sessions. Watch launchers print immediately and run unbuffered. Native graphical viewer behavior still needs testing on your PC.

Pause with 8 and wait for saving. Copy the ZIP's chat_gpt_ai/novaforge and chat_gpt_ai/triadbot into your existing Chat_GPT_AI, replacing program files. Keep .venv/assets/runs/exports. Close old watch consoles with Ctrl+C and close RLViser. No dependency reinstall or training reset is needed. Run 13 and send its ZIP; retry 1 for random Triad or 5 for the learned selector.

[Detailed diagnostic/watch instructions](NovaForge/DIAGNOSTICS_v1.9.1.md) · [Research plan](NovaForge/RESEARCH_v1.9.md) · [Validation](NovaForge/VALIDATION.md)

Individual source packages:

- [NovaForge v1.9.1](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.9.1.zip)
- [TriadBot v1.2.1](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.2.1.zip)

Source only: no models, private reports or user run data. Published on codex/novaforge-v1; main remains unchanged. The measurements are exploratory and do not establish an improved bot or native timing parity.
