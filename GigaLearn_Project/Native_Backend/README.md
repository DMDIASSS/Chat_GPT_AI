# Native GigaLearn + replay preparation

A tested CPU C++ training path for the pinned public GigaLearn archive, with a
fixed observation layout, replay pretraining/reset banks, bounded iterations,
resume, pause and throughput reports. New files/results stay under
`data/isolated/gigalearn_native/`. Original Nexto/Cycle9/update180 files remain
unchanged. This is a separate GigaLearn MLP lineage, not a direct continuation
of a native Nexto attention checkpoint.

## Windows setup

Extract the update into `E:\Downloads\Chat_GPT_AI`. Then:

1. `NATIVE_0_INSTALL_TOOLS.bat` installs pinned CMake/Ninja in your existing .venv
   and checks Python, Torch, compiler and collision meshes.
2. `NATIVE_1_FETCH.bat` downloads the pinned GigaLearn source into its isolated
   data folder and applies a hash-checked compatibility patch. It does not reuse
   or overwrite the older Research Hub's source/build/checkpoints.
3. `NATIVE_2_BUILD.bat` finds Visual Studio C++ tools using vswhere and builds
   Release/x64. If missing, install VS 2022 Build Tools with Desktop development
   with C++ and a Windows SDK. Two compiler jobs are used to limit RAM pressure.
4. `NATIVE_3_SMOKE.bat` starts eight CPU arenas, completes two PPO iterations,
   saves checkpoints and verifies actual completion and required files.
5. `NATIVE_4_BENCH.bat` benchmarks six iterations with 32 arenas. Read
   `data/isolated/gigalearn_native/runs/native_bench01/last_result.json`.

Each smoke/benchmark uses a new run name; repeating an existing name refuses to
replace it. Use the CLI with another `--run` for repeated tests.

The build uses LibTorch belonging to the same Python/PyTorch installation.
Python development headers and import/shared library are checked explicitly.
The standalone CMake target builds GigaLearn, RLGymCPP and RocketSim, without the
unnecessary RLBot executable. Compatibility fixes cover broken relative paths,
case-sensitive headers, monotonic timer types and portable C++20 iterator traits.
The patch refuses unknown contents instead of overwriting a customized checkout.
Windows CRLF and LF copies of the exact pinned source are both accepted. All six
source files must match known original or patched text before any line endings
are normalized. Actual code edits and partial patches still stop the setup.
If an older installer reports `Unexpected source contents` on an unedited
checkout, install the current update and rerun fetch/build; no source deletion
or hash-check bypass is needed.

CPU was built/tested with GCC 14, Python 3.12 and PyTorch 2.14.1. Windows MSVC and
CUDA execution remain local checks. For CUDA, use a compatible CUDA-enabled
PyTorch/LibTorch and CUDA toolkit; the helper checks the selected PyTorch install.
`--device auto` chooses CUDA when supported. CPU is the default smoke/benchmark.
Do not replace your main Python environment merely to experiment with CUDA.
The helper prefers venv CMake/Ninja over system tools. CUDA-enabled Torch builds
set both CMake's CUDA architecture and `TORCH_CUDA_ARCH_LIST` from readable GPUs,
avoiding empty architecture errors on repeated Torch discovery. If building
without a readable GPU, set a numeric `TORCH_CUDA_ARCH_LIST` explicitly (for
example `7.5` for a capability-7.5 GPU). Use a CUDA toolkit compatible with the
CUDA version reported by `torch.version.cuda`; do not infer it from driver version.

## Actual backend behavior

This uses GigaLearn's C++ PPO implementation. It trains all cars in self-play.
It uses a padded version of GigaLearn AdvancedObs with fixed teammate/opponent
slots and presence bits, so 1v1, 2v2 and 3v3 share the same input shape. Source
CPP networks can therefore continue in another game size after copying their
complete native checkpoint to a new run. This was tested for 1v1 to 2v2 and 3v3.

Tick skip is 8 with one tick action delay. Rewards emphasize goals, ball progress
and modest useful contact/approach shaping; large demo/touch farming weights in
the upstream example are absent. This first native release uses self-play, not
frozen Nexto opponents and not forced scripted kickoffs on PPO learners. The
existing Nexto export/trainer remains available with its scripted kickoff.

Default smoke/benchmark networks are 128-wide for controlled resource use.
`NATIVE_5_TRAIN.bat` starts a new 256-wide, three-policy-layer run for ten bounded
iterations. `NATIVE_6_RESUME.bat` continues it for ten more. `NATIVE_7_PAUSE.bat`
requests a checkpoint and exit after the current iteration. Sources and results
are hashed; changing binary or replay bank refuses resume. Native checkpoints
use `.lt` model/optimizer archives plus `RUNNING_STATS.json`.

A process exiting with code zero is insufficient: the runner requires the
completion marker, finite positive throughput measurements and a full saved
checkpoint. The patch also removes the noninteractive keyboard thread and adds
bounded iteration/pause handling, avoiding infinite console-less loops.

## Your current strongest Nexto actor

Native Nexto's attention tuple/network and GigaLearn's MLP are different. Renaming
`update_000180.pt` or exporting it as `POLICY.lt` cannot transfer its learned skill.
This release does not directly load/fine-tune native Nexto, distill a Nexto teacher,
or export the new MLP through the old Nexto browser/RLBot adapter.

Keep update180/current champion for play and comparisons. The C++ route provides
a new faster training lineage and human-replay initialization; accepting it as a
replacement needs independent matches and a validated inference/export adapter.
No policy is automatically promoted to the main project champion.

To continue one of this release's own native CPP checkpoints in a new mode/run:

```bat
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py train --run native_2v2_01 --players 2 --games 32 --steps 16384 --iterations 10 --initial-checkpoint "data/isolated/gigalearn_native/runs/native_smoke01/checkpoints/4832"
```

Use the actual checkpoint folder printed by your run. Network width/depth must
match. The original source checkpoint is copied, never edited. Older unpadded
GigaLearn checkpoint architectures require a separate conversion.

## Replicar and the curated high-level dataset

Replicar is a Rust converter with Parquet output and field provenance. The
upstream version here requires Rust 1.97+. Its Python reader needs Python 3.12+.

`REPLICAR_0_SETUP.bat` fetches commit
`a775fb1c4e5ee5c3079de3d0e6a16edb9335b71d`, installs the reader in the existing
.venv, then builds the native converter using `cargo build --locked --release
-p replicar-cli`. Install the official Rust toolchain first if needed. The
RocketSim Rust build may also require LLVM/libclang; point `LIBCLANG_PATH` to the
installed LLVM library directory when Cargo reports it missing. The cloud had
no Rust compiler and its package download was blocked, so native conversion was
not built/tested there; reader/Parquet integration was tested.

Convert local replays, keeping compact eight-tick rows:

```bat
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\native_setup.py replicar-convert --input data/replays --output data/replicar --jobs 2
```

Already converted compatible Replicar Parquet does not need the Rust compiler
on the machine that trains. Do not convert stripped files without the state,
game and updates groups. Match source hashes, control sources, freshness and
unknown values remain meaningful; fitted controls are not certified true inputs.

The curated [high-level dataset](https://github.com/Rolv-Arild/rl-high-level-dataset)
is available from its author's linked Kaggle page. Prefer that filtered corpus
over indiscriminate dumps. Its full collection pipeline needs Python 3.13 and
Ballchasing credentials; neither is required to train from downloaded local
files. This update does not scrape Discord or collect account tokens.

Select a bounded local sample from a downloaded mode folder containing JSONL
`metadata.json` and `.replay` files:

```bat
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\select_high_level.py --input "E:\path\to\downloaded\1v1" --out data/isolated/high_level_sample01 --limit 100
```

Selection ranks by upstream score, caps per-player exposure, checks duplicate
binary hashes and copies selected files. These scores reflect upstream curation,
not independently verified ranks. The source files are preserved.

## Replay pretraining and resets in C++

First prepare a native demonstration dataset using the existing pipeline, from
raw replays or converted Replicar Parquet:

```bat
.venv\Scripts\python.exe -u slater_versatile_trainer.py prepare --inputs data/replicar --out data/isolated/replicar_dataset01 --workers 2 --max-replays 100
.venv\Scripts\python.exe GigaLearn_Project\Native_Backend\prepare_bank.py --dataset data/isolated/replicar_dataset01 --out data/isolated/giga_replay_bank01.bin --players 2 --limit 10000
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py smoke --run native_replay_smoke01 --replay-bank data/isolated/giga_replay_bank01.bin
```

The Python bridge uses Replicar's actual Parquet reader/RLGym adapter, current
physics, controls, control provenance and update ages. It excludes future/final
outcomes from actor inputs. Raw replay and its converted Parquet cannot populate
separate dataset partitions. Missing airborne controls are not replaced by zero
labels. Replay-level train/validation/test groups remain separated.

The bank converts those current states into a checked C++ format. On load the
actual GigaLearn 90-action table must exactly equal the label action table.
C++ builds its own observation from each restored state, filters labels through
its own action mask and trains the policy/shared layers with confidence-weighted
cross-entropy. It selects the best validation-loss snapshot, including optimizer
state, before PPO. Validation CE is not competitive strength. The untouched test
partition does not train or supply reset states.

Twenty percent of PPO resets sample training-bank states, including ball/car
poses, velocities, boost timers and core jump/flip/wheel state. This is not a
lossless transfer of every Replicar/RocketSim hidden field or long-horizon parity
across RocketSim versions. `SLATER_REPLAY_RESETS count=` confirms use. The PPO
learner continues normally afterwards, refining demonstrations through play.

Start a larger replay-initialized run:

```bat
.venv\Scripts\python.exe -u GigaLearn_Project\Native_Backend\native_setup.py train --run native_replay_train01 --replay-bank data/isolated/giga_replay_bank01.bin --bc-epochs 2 --device auto --games 64 --steps 32768 --iterations 10 --width 256 --depth 3
```

Resume does not repeat BC. Use a new run/source copy for a changed dataset.
A two-player bank supports 1v1; use `prepare_bank --players 4` for 2v2 or `6` for
3v3 and the corresponding native `--players 2/3` setting.

The Parquet support changes the Python versatile trainer's code hashes. Finish
an active versatile run before installing this update, or retain its old code
for resume. Existing mechanics-trainer protocol files are unchanged.

## Evidence and next steps

The final padded CPU benchmark used 32 1v1 arenas, two Torch threads, six PPO
iterations and 128-wide networks: 115,968 agent action decisions. Warm median
collection was **92,235 decisions/s**; including collection and optimization,
**52,386 decisions/s**. Startup, serialization and framework/architecture choices
matter; these numbers do not establish a 15–50x controlled Nexto speedup or faster
skill improvement. Benchmark the same configuration on your laptop.

Actual C++ PPO, replay BC, replay reset use, save/resume and native checkpoint
continuation across 1v1/2v2/3v3 ran successfully. Replay BC and resets used exact
synthetic simulator captures as integration data, not SSL demonstrations. The
Replicar reader passed seven upstream checks, and the project adapter tests
exercise actual synthetic Parquet reading and future-label exclusion. See
`docs/NATIVE_GIGALEARN_VALIDATION.md` for details.

Next work: calibrate actual high-level replay reconstruction/controls, run larger
BC+RL comparisons, validate an inference/export adapter, and compare against
Nexto/update180 on fresh full matches. Fast collection enables these experiments;
no stronger playing bot or elite rank was established in this setup task.
