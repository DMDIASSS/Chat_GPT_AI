# GigaForge reward research Windows release

[Update an existing install](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Reward-Research-Update.zip) · [Complete project ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-GigaForge-Research-Windows.zip)

Pause older trainers. Merge chat_gpt_ai/gigaforge into the existing folder, replacing program/native files while preserving models, runs, assets and environments. Run 9_VERIFY, then 3_START_OR_RESUME. Missing runtime: 1_SETUP_GPU or 0_SETUP_CPU. The coordinator creates research01 from protected starting actors and preserves the halted native01 experiment. It searches reward profiles automatically, retires bad branches, continues after rejections and exports only retained champions. Default session budget is approximately five hours. Pause with 4, report with 8, retained watch with 5/6, candidates with 10/11 and exports with 7.

[Full instructions](GigaForge/RESEARCH_START.md) · [Research papers and exact scope](GigaForge/RESEARCH_PAPERS.md) · [Controlled pilot and validation](GigaForge/RESEARCH_VALIDATION.md) · [Release hashes](research/GigaForge-research-release.json)

Windows CPU correctness checks passed, including real native rollouts, policy updates, optimizer resume, eight reward/family combinations, candidate rejection and protected export copies. The short pilot prepared all 65536 collected samples but did not establish a stronger model. This is an empirical improvement search, not a 100% strength guarantee. New-build CUDA verification still runs on the user's PC. No teacher weights, user reports or API keys are published.
