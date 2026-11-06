# GigaForge Windows runtime and dependency reuse update

[Small update for an existing install](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Dependency-Reuse-Update.zip) · [Complete Windows ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Windows.zip)

Pause trainers, merge chat_gpt_ai folders into the existing project, then run gigaforge/12_FIND_LIBRARIES.bat and 1_SETUP_GPU.bat. Setup reuses working Python 3.11 x64 / PyTorch 2.9.1, references donor libraries through a separate repair environment if needed, checks local wheels/cache before new downloads, aligns W&B with NovaForge's pinned SDK, and saves one verified runtime for all launchers. Open 3_START_OR_RESUME after setup passes. Keep existing models, checkpoints, login and native01 run. CPU alternative: 0_SETUP_CPU. No learning settings changed.

[Detailed search locations, custom roots, repair and limitations](GigaForge/RUNTIME_UPDATE.md). Installed CUDA toolkits do not substitute for a compatible working Torch wheel; incompatible versions are skipped. No keys are read/copied. Donor environments must remain in place while referenced.

The native Windows executable is unchanged from successful workflow 42277845367. Actual native training/resume/parity passed on Windows and Linux. The dependency finder has separate Windows checks, including a real pip overlay test that leaves donor files untouched. User diagnostics confirm CUDA 2.9.1+cu126 runs; strength gains still require paired confirmation. No user uploads or weights published.

Small update SHA256: 14f841b2aaf7732e3ec4cd39d5dea8954f2a92bd5c5cbff969696bf064a43bb4

Complete ZIP SHA256: e15b281c8e153180e3a83d486e1faed682c85672bd21c12a477e669e6e0ed950
