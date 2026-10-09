# Chat GPT AI — Native Nexto Baseline + PPO Fine-Tuning (experimental)

## Why this replaces the old student experiments

The old 92-input imitation students recorded 0 wins in 20 first-to-score episodes versus Nexto, with tiny fractions of the total ball contacts. V2's raw contacts went 8 → 20 but Nexto contacts also went 472 → 1220; normalized student contact share **decreased** (8/480 vs 20/1240). Treat that student architecture as a failed path, not a Nexto-level model.

**This add-on loads and fine-tunes the original Nexto attention-based TorchScript policy**, so the unmodified baseline starts with the same actor weights and same original observations as the Nexto opponent. The PyTorch JIT module provides trainable parameters; tests verified forward inference and gradient propagation. No 92-input imitation student is involved.

The learned policy is trained experimentally with clipped PPO, a small independent value network, and a frozen-Nexto KL regularizer to *limit*, not prevent, catastrophic forgetting. Its reward values are experimental. **No claim that the tuned actor beats Nexto.** Progress must be measured by the benchmark, not loss/reward alone.

## Requirements

Use your **existing** `E:\Downloads\Chat_GPT_AI` installation, including:

- `nexto_teacher.py` and `vendor\nexto\nexto-model.pt` from the earlier Fast Track add-on.
- The installed `.venv` with `torch`, `numpy`, `rlgym`, and RocketSim integration.
- RLViser for optional rendered watching.

Extract the contents of this ZIP **directly into the project folder**, beside `train.py` (don't create a nested subfolder and don't delete the old data). The six batch files use your existing `.venv`. There is no new Internet download required.

## Recommended Windows sequence

1. **`CHECK_NATIVE_SETUP.bat`** — verifies original model + imports.
2. **`NATIVE_0_BENCHMARK.bat`** — Nexto-native actor vs identical frozen Nexto (20 first-to-goal episodes). It should be approximately fair across sides. Report counts and normalized contacts.
3. **`NATIVE_WATCH_ORIGINAL.bat`** — optionally watch this *already strong* baseline in RLViser. This does not change any weights.
4. **`NATIVE_1_SMOKE_TRAIN.bat`** — 1,024 actor decisions with PPO against frozen Nexto; saves only to `data\native_nexto\last.pt`. Designed as a compatibility/stability test, not a skill improvement guarantee.
5. **`NATIVE_2_BENCHMARK_TUNED.bat`** — exact same first-to-score format and seed as baseline. Compare **win counts, contact rates per 1,000 decisions**, and whether it still acts intelligently.
6. **`NATIVE_3_RESUME.bat`** — only after you verify the tuned actor isn't worse. Increase to 10k *cumulative policy decisions*.

To watch the tuned policy: `NATIVE_WATCH_TUNED.bat`.

## Why first-to-goal matches are not full match win rates

Each episode runs for up to 750 8-physics-tick decisions (50 seconds simulated), stops on the first goal, and swaps teams by episode. In particular, a raw touch count is NOT enough: shorter episodes have fewer opportunities to touch the ball. This revision prints touches **per 1,000 decision ticks** and total durations in addition to wins.

## GPU and performance

For your 4-core i5-10300H and GTX 1650 Ti Mobile, the launchers default to CPU and two torch threads. That can be faster and quieter for tiny single-environment inference, whereas CUDA can help large-batch PPO but add overhead and heat. **Benchmark** on your laptop before choosing one. For manual CUDA testing, replace `--device cpu` with `--device cuda:0`; the original frozen teacher remains on CPU.

This is NOT the promised high-speed GigaLearnCPP implementation. It prioritizes getting a functioning Nexto-quality starting policy immediately; training throughput is a separate optimization. A faster engine isn't useful if the learned student can't drive. C++ remains a potential later backend after preserving Nexto's native observation/actor semantics.

## Safety and preserved work

- The original Nexto actor is read only from `vendor\nexto\nexto-model.pt`.
- The existing human replays, `data\bc_policy.pt`, 92-input PPO checkpoints, and student models remain untouched.
- Fine-tuning checkpoints are stored separately under `data\native_nexto\`.
- Only intended for simulated games and offline bot matches, **not online ranked matchmaking**.
- Nexto original model and derived weights are subject to the upstream **Creative Commons Attribution-NonCommercial-ShareAlike 4.0** licensing terms. Preserve attribution and license notices; this project is not cleared for commercial use.

## Problems to report

If anything crashes, copy the first traceback or error. The TorchScript `FutureWarning` is not a failure. If the native-actor baseline doesn't achieve roughly comparable results to frozen Nexto, stop and report that first; do not run PPO.

### Experimental limitations

Native Nexto uses the original attention observation, including previous actions and boost pad information. We have only verified JIT inference, parameter gradients, and checkpointing in this environment. **Real RocketSim PPO rollout compatibility is not verified here** because the simulator bindings aren't installed. This isn't yet specialized aerial/flip-reset training, and directly fine-tuning a strong model can reduce its skill unless carefully evaluated.
