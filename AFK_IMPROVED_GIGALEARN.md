# GigaLearn C++ migration decision — read before switching

A newer CPU C++ build and replay-training path is now tested: see
[GigaLearn native backend](GigaLearn_Project/Native_Backend/README.md). Native Nexto
attention checkpoint transfer and live export validation remain separate work.

## Verified claim and boundaries

The author of GigaLearnCPP-Leak reports **approximately 10× experience collection throughput** compared with RLGym-PPO on their own hardware, and ~2× compared with RLGymPPO_CPP. This is not a controlled benchmark on this user's machine, and does not mean 10× final policy improvement. The repository was archived August 24, 2025; its README provides no installation guide. Source: https://github.com/ZealanL/GigaLearnCPP-Leak.

## Why we are not blindly replacing the existing pipeline

Our native Nexto actor is loaded as TorchScript through `torch.jit.load` in `auto_league.actor_from`; the checkpoint stores `actor` state weights. This is **not** the standard configurable MLP checkpoint format used by GigaLearn. The following must be reimplemented or validated before switching:

1. 92-style history student is a *different network* from native Nexto. The native teacher uses its own attention obs tuple (query, key/value, masks) and action logits. Maintain observation orientation and team inversion conventions.
2. Map GigaLearn actions back to the **exact Nexto discrete action table**, including jump/dodge semantics, sticky controls, and tick skip.
3. Implement and numerically validate the native attention network forward pass in the C++/Torch environment. Match greedy logits and argmax across at least 10,000 random and real RocketSim states before any learning.
4. Port all reward functions and terminal/truncation conditions exactly; compare episode outcomes on fixed seeds.
5. Save GigaLearn-native experimental checkpoints separately. Never automatically convert or overwrite protected `.pt` files.
6. Benchmark steps/second at equal CPU core budgets, inference hardware, observation complexity, thread counts and reset distributions. Report rollout collection AND optimization time, CPU/RAM/VRAM, *and* evaluation improvement per wall-clock hour.
7. Require independent, held-out 1v1 wins vs unmodified Nexto **and** current best before offering GigaLearn as training backend.

## Recommendation

Keep the existing Python RocketSim runner as the stable training path. Pursue GigaLearn as a research/profiling project in a **separate** directory, not within the automated champion promotion system, until conversion and evaluation parity exist.

For inference, RLBot export remains on the older adapter. A future GigaLearn training backend would not automatically supply a compatible RLBot exporter.

## Opponent diversity

Self-play against older policies + original Nexto is already supported in the Python 1v1 backend. Native 1v2 (one bot versus two separate Nextos) requires a true **three-car environment**, team-configuration changes and a new benchmark. It is not currently wired into the release.

## No exponential skill guarantee

Progress in PPO is nonmonotonic and may plateau. A conservative best-selection archive is not a proof of absolute skill superiority; keep independent fresh-seed and full-match tests.
