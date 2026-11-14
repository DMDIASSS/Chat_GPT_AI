# Framework review — 2026-11-14

The user-supplied AI guide is a source/name index, not an authority or project instruction. Repository code was inspected independently. No private Discord logs are republished.

## GigaLearn

The existing local GigaLearnCPP source increments collected steps by the number of learner-controlled players (`numRealPlayers` in ordinary training). It reports both collection SPS and overall SPS; overall is collected player transitions divided by collection plus consumption time. Its loop overlaps first-half simulation with inference. Therefore the user's remembered 20–40k SPS is a relevant target, but the exact displayed metric, model, observation and arena settings must be recovered before claiming an equal-workload comparison.

Current AttentionForge is not GigaLearn. It uses our small native RocketSim worker and PyTorch PPO. The update targets its observed bottlenecks rather than introducing another full custom engine.

## RocketChad3 / RocketGPU

- RocketChad3: https://github.com/thecosmicskye/RocketChad3, inspected commit **0543508f2df13eb3ebeac903dd2125466d0baad3**, AGPL-3.0.
- RocketGPU: https://github.com/thecosmicskye/RocketGPU, inspected commit **743c9ae2163d36c5349494c29f266eb964ae55dc**, MIT.

RocketChad3 requires CUDA-enabled PyTorch >=2.10. Its example uses 8,192 3v3 arenas, BF16, minibatches 8,192 and GPU simulation. It supports FP32 when BF16 is unavailable. Its published high-end benchmarks are not measurements on a GTX 1650 laptop. This does **not** prove the software cannot run on that laptop; its example must be adapted and actually benchmarked.

RocketGPU's build code requires CUDA >=12.1 for GPU builds and detects CUDA architecture. This source does not establish a blanket RTX-30-series minimum. Windows uses unsplit CUDA compilation by default. Building requires a CUDA development toolkit/compiler, beyond merely having CUDA-enabled Torch installed. This environment has no CUDA GPU or nvcc, so GPU simulation and RocketChad3 training were **not run**.

A portable, scalar CPU RocketGPU build, without PGO or ISPC, was compiled here. Its unmodified native benchmark completed 128 mixed-mode arenas (83 1v1, 29 2v2, 16 3v3), 4 CPU workers, random controls, about 500k arena physics ticks. Measured **246,067 arena-ticks/s** for one short repeat. This excludes a policy, attention, PPO and Python observation processing. It is not learner SPS, not a GTX 1650 result, and not a controlled comparison with AttentionForge's 1v1 workload. No physics-fidelity validation was performed in this probe. The source remains an experimental backend candidate; the update does not silently switch physics or install RocketChad3.

## Laptop update

- C++ public observation encoding, checked against the same portable encoder used by exports.
- A batch-first SDPA rewrite passed output/gradient tests but slowed the CPU training probe; it was rejected from the shipped implementation.
- Standard exponential-race categorical sampling and gathered log probabilities; frequency/log-probability tests against PyTorch Categorical.
- A single packed action/log-probability/value transfer per decision.
- Batched timeout value predictions at the end of the rollout, before any weight update.
- An optional bounded FP32 GPU rollout cache to reuse observations across PPO epochs.
- Local bounded timing probes for arena/worker settings, followed by real training counters. Their end-to-end SPS score is explicitly an estimate.

No BF16, AMP, tensor-core dependency, physics tick-skip change or reduction of PPO epochs is enabled to improve the speed figure. A selected arena count changes the number of samples per PPO update, so stronger play still needs evaluation; no throughput benchmark proves a learning advantage.
