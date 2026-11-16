# Supplied project and predictive-potential brief review — 2026-11-16

This is a source review, not a new predictive reward implementation or a CUDA build fix. The watch diagnostic patch changes no trainer or weights.

## Existing functional foundation

The supplied DuelForge Colab archive preserves the exact native/core.cpp, train.py, model.py, observation.py, learning.py and runtime.py from DuelForge 0.3. The CMake change removes the Python-3.11-only build restriction; Linux setup builds an interpreter-compatible .so. It is a Colab wrapper around the same CPU-simulator/GPU-PPO trainer, not GPU-native simulation. Shell syntax checks pass. A notebook is described in the README but was not present in either uploaded ZIP. Do not treat an advertised notebook as an included file.

The current DuelForge model is a 109-feature, 90-action, separate dense actor/critic checkpoint with optimizer/RNG/counters. The supplied RocketForge config instead creates 128-wide depth-one entity attention through RocketChad3. Direct checkpoint interchange is unsupported. Any conversion or distillation needs explicit feature/action/logit tests.

## RocketForge GPU archive

Nine support/configuration files; upstream trainer and physics are retrieved at setup, not included. Its four CPU support tests pass, covering numeric checkpoint selection, environment path handling, mesh discovery and synthetic reward tensor shape. They do not test a CUDA compiler, GPU physics, real training, timeout handling, export or playing strength.

Verified upstream source:

- RocketChad3: https://github.com/thecosmicskye/RocketChad3/tree/2d37c06d43875158f8b8d8832ad2ce2c37e7274f (AGPL-3.0). Requires Python >=3.10 and Torch >=2.10. Precision supports FP32 and BF16; FP32 is the appropriate supplied choice for T4.
- RocketGPU: https://github.com/thecosmicskye/RocketGPU/tree/743c9ae2163d36c5349494c29f266eb964ae55dc (MIT). This is the same revision named in the failed CUDA build report. The README's performance/accuracy numbers are the author's measurements on specified hardware, not verified T4/GTX1650 results here.

Issues relative to the new brief:

1. rewards.py pays goal differential plus ball velocity toward goal and a warmup speed-to-ball term. It contains no shared trajectory prediction, interception estimator, previous/next state potential, shot availability or pressure estimate.
2. Directional velocity rewards are not exactly zero-sum away from field center: a ball moving toward the center from the side can have positive projections toward both goal directions.
3. config.py explicitly sets timeout_bootstrap=False. That does not meet the brief's request for time-limit bootstrapping; its interaction with upstream phase/terminal behavior needs verification before changing it.
4. The supplied state setter is upstream's kickoff-only default. It does not provide the requested varied midfield, defense, aerial and wall starts.
5. setup.py shallow-clones moving default branches, and reuses existing checkouts without enforcing a source revision. Printed hashes help diagnosis but are not reproducible pins.
6. setup.py can upgrade Torch in the selected environment and remove an existing build directory after an import failure. An isolated environment/build directory and preservation of failed build logs would fit the new brief better.
7. Stop handling uses process termination; it does not establish that an interrupted update saves a fresh, internally consistent checkpoint. Timed saves are the known fallback in this wrapper.
8. The ZIP contains no RLBot export or evaluator implementation, despite requiring both for a complete project.

No CUDA build was retried here. This environment has no NVIDIA GPU/toolkit, so the T4 typed-pointer compiler failure cannot be reproduced or fixed with verified results here. Do not repeat the already failed CUDA 12.8/13.0, split/on-off and optimization/on-off matrix without a new minimal reproduction and testable hypothesis. GPU compilation remains separate from reward development on the working CPU backend.

## Interpreting the requested reward

The brief calls for a versioned new objective: goals plus gamma*Phi(next)-Phi(current), with bounded, side-antisymmetric interception, shot and pressure potentials. It is materially different from both the existing DuelForge contact/approach bootstrap and RocketForge's velocity reward. Neither existing archive implements it.

A sound implementation sequence is interception in isolation, validation against real simulated reachability, resource-bounded refinement, then separately ablated shot and pressure terms. Estimated feasibility should expose uncertainty; a heuristic should not be labeled an exact first-touch solver. The same decision discount must be used, true goals need absorbing terminal potential, truncations retain the final physical potential and bootstrap value, and reset states must not enter the previous episode's shaping difference. Correct PBRS algebra does not by itself prove finite-budget learning improves.

The shared prediction cache must be deterministic from the declared state/history, or that predictor memory must be treated consistently as part of the learning state; arbitrary stale prediction rewards undermine the simple stationary-Phi argument. Limited candidate rollouts may find feasible contacts without proving all other contacts impossible.

Preserve original runs and actor/optimizer files. Introduce the predictive reward only in a named fork/new experiment, log every potential component and estimator failure, benchmark full learner throughput with and without it, and validate on fresh-seed actual outcomes. The proposed 0.60/0.25/0.15 weights remain hypotheses.
