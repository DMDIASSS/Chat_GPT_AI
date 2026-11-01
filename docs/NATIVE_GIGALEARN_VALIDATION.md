# Native GigaLearn validation — 2026-10-12

## Build

GigaLearn source: `86e11c3881a21225a43c36b14af40f0b3c87e7dd`.
Actual Release C++ build completed using GCC 14.2, CMake 3.31.6, Ninja 1.11.1.4,
Python 3.12 and CPU LibTorch from PyTorch 2.14.1. Collision meshes came from the
existing RLGym installation. No CUDA GPU was available.

The standalone target built GigaLearn/RLGymCPP/bundled RocketSim and the new
entrypoint. Six upstream files required hash-checked compatibility changes:
bad relative/case-sensitive includes, monotonic timer types, C++20 iterator
traits, and bounded/noninteractive/pause handling. No verification was disabled.
The helper build path was exercised; binaries/libraries linked and executed.

## Final padded-layout runs

- Replay-enabled CPU smoke: 8 1v1 arenas, two Torch threads, two PPO iterations,
  **4,832 per-agent eight-tick action decisions**. Policy/critic/shared-head
  weights and all optimizer files were saved.
- Replay BC used synthetic exact simulator captures. 130 feasible training and
  12 validation examples survived the C++ action mask. Validation CE moved from
  **4.73026 to 4.72021 to 4.70901**. This is an integration result, not human skill
  evidence. The best validation model/optimizer snapshot was restored before PPO.
- Replay reset counters were **2 then 4**, confirming actual training-bank resets.
- Resume completed iterations 3–4 and saved **9,664 total action decisions** with
  changed policy weights. The helper verified completion plus required files.
- Native checkpoint copying continued the 1v1 model in **2v2** and **3v3** with
  the same padded input architecture; both ran two additional PPO iterations
  and produced complete new checkpoints. Source snapshots remained unchanged.
- Final CPU benchmark: **32 1v1 arenas**, two Torch threads, 128-wide network,
  six iterations, **115,968 total action decisions**. After excluding the first
  warm-up iteration, median collection was **92,235.22 decisions/s**; median
  collection+optimization throughput was **52,386.48 decisions/s**. Total process
  wall time was 2.70 s, including startup/checkpoint writes. These measures count
  every trained car; they are not learner-only Python throughput measurements.

GigaLearn's smaller MLP, observations, rewards, all-car self-play, and bundled
RocketSim differ from the existing native Nexto attention trainer. No controlled
15–50x Nexto speedup or faster skill improvement was established. Reproduce a
matched benchmark on the user's laptop, including CUDA if desired.

## Replay data

Replicar commit: `a775fb1c4e5ee5c3079de3d0e6a16edb9335b71d`.
Its Python reader was built/installed and **seven upstream reader tests passed**.
The project Parquet adapter uses the official reader and RLGym bridge. Tests use
actual synthetic Parquet, verify current states/actions, exclude future scores,
and reject unknown airborne controls. Raw/converted versions of one replay are
deduplicated before partitioning. Action-table equality is checked in C++.

The curated high-level dataset source was reviewed at
`a5197c80d24b8ebbf5608d2c62596465c9d5f159`. A bounded local selector uses its
published JSONL metadata, quality scores and per-player exposure caps; no Kaggle
or Ballchasing corpus was downloaded and no account credentials were requested.

Project tests: **26 passed** across `test_native_setup.py`,
`test_replicar_integration.py`, and `test_versatile_trainer.py`. The existing
versatile simulator/BC/resume/observation parity checks remain in that count.
Python/C++ source and patch-content checks passed.

## Concrete limitations

Replicar native conversion requires Rust 1.97+; the cloud had no Rust toolchain.
The Debian toolchain download failed with proxy HTTP 403. PyPI also had no
matching prebuilt replicar-native distribution. Native Rust conversion was not
built or validated here; use the Windows setup with a real supported Rust/LLVM
toolchain, or bring already converted compatible Parquet.

Windows MSVC build, CUDA compilation/execution, real high-rank replay learning,
competitive strength, native Nexto attention transfer, frozen Nexto opponents,
scripted self-play kickoffs, and an inference/export adapter for this new MLP
remain unvalidated or unimplemented. The working native release is self-play
with optional replay BC/resets and native save/resume. It does not replace the
existing best playing bot automatically.

Core poses/velocities/boost/jump/flip/wheel state transfer through replay banks;
not every Replicar hidden simulator field is restored. Cross-version/platform
RocketSim long-horizon fidelity is not certified. All original Nexto/source
models remain unchanged. Protected Nexto remains SHA256
`bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa`.
