# DuelForge — a new Rocket League 1v1 research project

**This download is the Phase 1 research/feasibility package. It is not a trained bot or a complete trainer.** The supplied prompt explicitly asks for an architecture and resource proposal before expensive training. No existing bot or reward configuration was imported, and no long training was started.

Read **ARCHITECTURE.md** first. **FIRST_EXPERIMENT.json** specifies the proposed 90-minute budget and approval boundary. **REWARDS.md** defines a fresh, small reward experiment with precise formulas/exploits. **research/** contains source pins, actual GigaLearn GAE audit findings, visualization/RewardServer feasibility, opponent contracts and evaluation rules. **results/** contains actual server microbenchmarks and validation results.

## Contents verified here

- Inspected source and exact revisions for native/Python/Rust framework candidates, RocketSim viewers and RewardServer.
- Compiled and ran the archived GigaLearn GAE function unchanged in an isolated real-LibTorch harness: reproduced reversed timeout bootstraps and an AddressSanitizer terminal read overflow. A minimal patch corrects those isolated fixtures; it is not a complete learner certification.
- Ran bounded synthetic forward/backward/Adam comparisons for three 1–3M parameter models. These are CPU measurements on the research machine, not GTX 1650 or game-training SPS.
- Ran a warmed physics-only RocketSim-binding probe. This excludes observations, rewards and learning.
- Ran eight mathematical/model unit tests. No measured playing-strength improvement, trained policy, live RewardServer plugin, graphical viewer connection or RLBot game-client test is claimed.

## Optional laptop benchmark — no game training

Extract into E:\Downloads so `chat_gpt_ai\duelforge` sits next to your existing `attention_skills` and `gigaforge` folders. It does not replace them.

Run **RUN_BENCHMARK_ONLY.bat**. It uses `py -3.11` to locate an existing Torch runtime in bounded nearby project folders, preferring a CUDA-capable environment. It does not install CUDA/Torch, scan your drives, read keys or resume old training. It prints the device and GPU name and writes **DuelForge_preflight_*.zip** inside duelforge. This ZIP contains the local model timing/resource measurements and can be shared for architecture selection.

If the Windows Python launcher is unavailable, use your existing Python directly:

```
"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" tools\preflight.py --python "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe"
```

The probe runs short synthetic tensor updates on disposable randomly initialized models; it does not teach a game bot or save weights. Expect roughly tens of seconds to a few minutes depending on imports/runtime discovery. GPU speed remains unknown until this local probe runs, and this probe alone still does not measure a complete training pipeline.

Tests with an existing Python containing Torch:

```
python -m unittest discover -s tests -v
```

The optional `tools/physics_probe.py` needs existing RocketSim Python bindings and collision meshes; it never downloads game assets. The GAE sanitizer reproducer is an optional Linux development harness documented separately and is not run by the Windows benchmark.

## Proposed implementation after research review

Fresh Octane policy; native RocketSim collection; small audited LibTorch PPO core; ~1.22M-parameter dense baseline; full observation/action/delay parity; outcome-first rewards; history self-play; independent confidence-aware evaluation; asynchronous RocketSimVis/reward inspection; atomic checkpoints, watch/report/pause and RLBot v5 native inference export.

The Windows build, local GPU profile, complete collector/optimizer benchmark and live-client smoke test remain work for the implementation phases. Nothing here promises a pro-level bot in a fixed number of hours. The first controlled pilot tests whether the foundation learns correctly and whether the proposed bootstrap term helps.
