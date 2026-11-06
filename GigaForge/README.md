# GigaForge reward research

This release keeps two independent actors: Chronos on Breakout and Galactus V2 on Octane. It adds all-sample bootstrapped rollouts, a small serial population of reward/learning-rate variants, bounded reward coefficient mutation, frozen/current/history opponents, teacher anchoring, resumable branches, W&B match metrics and protected exports.

[Start and resume instructions](RESEARCH_START.md) · [Paper-to-code mapping](RESEARCH_PAPERS.md) · [Pilot and validation](RESEARCH_VALIDATION.md) · [Dependency reuse](RUNTIME_UPDATE.md)

Merge the ZIP's chat_gpt_ai folders into your existing project. Preserve environments, assets, models, runs and exports. The new native executable is included. Run 9_VERIFY, then 3_START_OR_RESUME. If a runtime is missing, run 1_SETUP_GPU or 0_SETUP_CPU; compatible existing libraries are reused. The new run is research01; existing native01 remains separate and its halt is not erased. The coordinator runs for approximately five hours per session, or until paused/error. A rejected branch is retired automatically while the search continues.

Pause/report/watch/export target the active research run. Watch retained champions with 5/6, unverified candidates with 10/11, export two independent v5 actors with 7, and send diagnostics with 8. Exports contain complete TorchScript .lt/.pt actors, TOML/loadout and loaders; no training critic or reward program is needed in RLBot.

Prepared/collected data use reached 100% in the controlled checks and pilot. Actual optimizer sample-use counts are logged separately. This does not guarantee stronger play. The short public pilot found no confirmed winner and retained both starting parents. A new candidate needs positive paired screening and fresh confirmation before replacing its retained champion. Repeated statistical comparisons are approximate; no universal or lifetime strength guarantee is claimed.

The Windows CPU build and controller checks passed. The user's earlier CUDA runtime works; this new executable must still pass the target GPU verification before a long GPU run. No laptop SPS promise, model downsizing or reduced PPO epoch count is used.

Source build: Python 3.11 x64, Torch 2.9.1, Visual Studio 2022 C++ Build Tools, then python tools/build_native.py. The builder fetches a commit/SHA256-pinned GigaLearn archive, applies explicit reviewed changes and builds Release. The native simulator is RocketSim 2.1.1; Python viewing/live adapters use RocketSim 2.2.1. Exact physics equivalence and live playing strength are not established by feature parity.
