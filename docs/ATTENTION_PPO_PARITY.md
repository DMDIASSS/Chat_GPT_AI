# Native attention PPO validation

This adapter trains the original TorchScript attention actor through LibTorch. It reuses the project's Python PPO objective: clip bounds 0.85–1.15, entropy weight 0.003, temperature 1.5 frozen-teacher KL, per-state teacher weight, population-standardized advantages, SmoothL1 critic loss and gradient norm bound 0.5. Gamma 0.995 and GAE lambda 0.95 are unchanged. Timeout rewards add gamma times the next value before terminating that episode's GAE chain. Each arena's advantages are computed separately.

The initial actor weights are exactly preserved. The 12-head critic is 80→192→192→12 with Tanh, matching VersatileCritic. Critic and Adam states start fresh. The normal-match observation/action/reward contract is preserved; replay imitation and new mechanic rewards are disabled in this milestone.

Actual fixed-input cross-language tests used original Nexto in cloud. Pre-update logits, critic values, advantages and returns matched exactly. One full-batch PPO step matched Python's updated logits within 2.67e-5 and critic values within 1.5e-8. The small post-update difference reflects floating-point reduction/minibatch row ordering; it is not a claim of bit-identical Python/C++ training trajectories.

Save/load testing restored both Adam states and CPU sampling RNG. The next sampled actions/log probabilities, next actor parameters, critic values and update metrics were bit-identical within the C++ implementation. All 44 actor tensors changed during the tested update; the teacher remained unchanged. A deliberately excessive policy update was rejected, and actor weights plus Adam moments were restored exactly while valid critic updates were retained.

Two defects were caught and corrected: TorchScript profiling/fusion warmup changed floating-point gradients after reload, so native training disables that graph optimization; C++ Adam's load merges its state map, so rollback explicitly clears it before restoring the saved archive. Tests exercise the empty pre-first-update Adam state as well as a populated state after training.

`ATTENTION_NATIVE.bat parity --run attention_parity01` executes actor-output checks, 108 real simulator-state observation fixtures/432 player views, and the fixed-input PPO/optimizer/RNG/rollback test. Its synthetic PPO test changes only a private in-memory actor and its diagnostic checkpoint. It does not promote that fixture as a playing model.

Complete training checkpoints are atomic directories containing actor, frozen teacher, critic, both optimizers, CPU/selected-device RNG, protocol and progress metadata. Incomplete writes are excluded from resume; a resumed run preserves interrupted partial directories under a new diagnostic name. Physical arenas are reset to deterministic next episode seeds at the resume boundary; exact continuation of a partially played match is not claimed. In-process training preserves active arenas across PPO updates.

CPU C++ builds and integrated collection/training/resume/evaluation/export were exercised. Windows/CUDA training on the user's actual update180 still needs the local build/parity/smoke commands. The user's earlier Windows forward/gradient probe is useful evidence but does not replace those full-trainer checks.
