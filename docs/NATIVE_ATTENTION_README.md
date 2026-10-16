# Native attention continuation

This is a separate native C++/LibTorch experiment that starts with the **actual
original attention actor**. The original normal-match migration now also supports
mixed practice routines, variable team rosters and frozen recent self-play. Your existing attention, MLP, AutoLeague and
replay runs are left intact. The playing model remains update180 until a separate
evaluation justifies changing it.

For the desktop interface, staged checkpoint selection and automatic champion
branches, start with [Training Studio](TRAINING_STUDIO.md). Its campaign keeps
the parent eligible, preserves every complete checkpoint, confirms improvements
on fresh seeds and rotates away from stalled routines. Manual commands below
remain available. Whole teams use frozen teammates; only the selected learner
contributes PPO experience, with its seat rotated between normal episodes.

The default source is:

```text
data\isolated\mechanics_curriculum\selected7_mechanics01\update_000180.pt
```

Missing source files produce an error. There is no automatic Nexto fallback.
The launcher exports the actor privately and checks every parameter against the
source. The teacher is an independent frozen copy of the source. Frozen rivals
use scripted kickoffs; the learner does not. Human replay gradients are **off**.

## First run on Windows

Pause other training to avoid competing for GPU, CPU and RAM. Extract the update
into `E:\Downloads\Chat_GPT_AI`, preserving the `GigaLearn_Project` and `docs`
subfolders. Existing training data and checkpoints are not part of the update.
Open CMD:

```bat
cd /d E:\Downloads\Chat_GPT_AI
ATTENTION_NATIVE.bat build
ATTENTION_NATIVE.bat parity --run attention_parity01
ATTENTION_NATIVE.bat smoke
```

If your planned training device is CUDA, also run a separate small GPU smoke:

```bat
ATTENTION_NATIVE.bat smoke --device cuda
```

To check the native GPU forward pass against the CPU reference explicitly:

```bat
ATTENTION_NATIVE.bat parity --run attention_cuda_parity01 --device cuda
```

Default parity runs on CPU. The original traced action head embeds a CPU device
for its constant action features; the native loader normalizes that device
to the selected CPU/CUDA device in private actor, teacher and rival instances,
including checkpoint reload. Actor weights and original files are unchanged.
GPU kernel execution still requires a successful local CUDA parity/smoke check.

The build initializes the installed Visual Studio x64 toolchain. It uses your
existing PyTorch, CUDA configuration and RLGym collision meshes. An intact pinned
GigaLearn source checkout is reused without being edited. If no previous source
checkout exists, a separate pinned checkout is downloaded under the new native
attention folder. Unexpected source edits are rejected and preserved.

The parity command checks portable actor inference, 108 real-state observation
fixtures covering 432 player views, and PPO/GAE/critic/optimizer/RNG/rollback
checks. These correctness tests do not establish stronger play. The smoke
is two real PPO updates, with complete checkpoints, in its own timestamped run.

Then run a bounded experiment:

```bat
ATTENTION_NATIVE.bat train --run update180_attention01 --updates 100
```

The default profile uses 8 match worlds, 128 learner decisions per world per
update, actor learning rate `3e-6`, critic learning rate `1e-4`, teacher anchor
`0.1`, and target rollout KL `0.005`. Actor weights are inherited; the critic and
optimizers start fresh. The source checkpoint is never rewritten.

## Pause, resume and compare

From another CMD window:

```bat
cd /d E:\Downloads\Chat_GPT_AI
ATTENTION_NATIVE.bat pause --run update180_attention01
```

Wait for the running process to print its completion marker. Pausing waits for a
safe update boundary and a complete checkpoint. Resume adds a **new bounded
budget** to the saved cumulative update count:

```bat
ATTENTION_NATIVE.bat resume --run update180_attention01 --updates 100
ATTENTION_NATIVE.bat status --run update180_attention01
ATTENTION_NATIVE.bat eval --run update180_attention01 --eval-seeds 8 --seconds 60
```

Evaluation compares the candidate and protected original using matched seeds,
both colors and frozen opponents. These are development screens. Use additional
fresh seeds and longer matches before replacing the playing model. A lower KL,
higher reward, successful save, or finished training budget does not guarantee a
stronger model. No automatic model promotion occurs.

Source, teacher, rival, native code, binary, runtime and profile identities are
pinned. Changed binaries/settings cannot silently resume an old run. Keep the old
run and start a new run name after an implementation change. Resume restores the
actor, critic, optimizers and RNG; partially completed episodes may restart at a
checkpoint boundary, so it does not promise identical future trajectories.

## Files and export

Everything new lives under:

```text
data\isolated\native_attention\build\
data\isolated\native_attention\runs\update180_attention01\
```

The run contains `protocol.json`, `progress.json`, private initial/teacher/rival
actors, native logs, `session_summary.json`, and complete checkpoint directories:

```text
checkpoints\checkpoint_000040\
```

A complete native attention checkpoint contains actor, critic, both optimizer
states, RNG, protocol and training state plus a completion marker. Keep the whole
directory for resume, not just `actor.pt`. Incomplete directories are ignored.

To make a standard attention checkpoint for existing project tooling:

```bat
ATTENTION_NATIVE.bat export --run update180_attention01
```

The exported `.pt` is placed in the isolated run folder and its actor weights are
checked exactly against the native TorchScript actor. This is a model export;
scripted kickoff remains a deployment/controller option rather than a learned
weight inside the checkpoint.

## Measure speed honestly

```bat
ATTENTION_NATIVE.bat benchmark --run attention_benchmark01 --device cpu --updates 3
```

This runs native attention PPO and a Python/PyTorch reference using the same
starting attention actor, match workload, game count and decision budget. It
records collection and optimization measurements in `benchmark.json`. The
bundled native RocketSim is 2.1.1; the Python simulator may be another version.
Initial actor/critic weights, CPU sampling RNG and kickoff permutations are
shared. Simulator versions, subsequent sampled trajectories and minibatch
ordering can still differ. Native totals include checkpoint I/O; Python phase
timings exclude it. These results are context for local tuning, **not a verified
identical-simulator speed ratio**.
They are never compared to the old weak MLP or raw simulation ticks as though
they were the same complete training job.

## Scope

This milestone is native attention training, checkpoint restoration, protected
sources and meaningful match evaluation. Replay imitation, reward changes,
mechanics curricula and full coordinated multi-car training should be separate
measured additions after this migration passes locally. Results from a short
cloud test do not establish improvement of the user's actual update180.

## Executed cloud validation

The complete CPU build passed. Native PPO collected real experience, changed
weights, saved full checkpoints, resumed, evaluated and exported a compatible
attention checkpoint. Fixed-input C++ optimizer/RNG continuation was bit-exact;
the frozen teacher stayed unchanged. Relevant tests are recorded in
`docs/ATTENTION_PPO_PARITY.md`, `ATTENTION_OBS_PARITY.md` and
`ATTENTION_TIMING_PARITY.md`. No user checkpoint was overwritten.

A short 8-world, 128-step, 3-update CPU benchmark measured approximately 1,590
native learner decisions/s during collection and 426/s including optimization
and checkpointing, versus 455/s collection and 245/s optimization-inclusive
Python phase throughput. This is a single cloud workload, not a laptop/GPU
speed promise, strength result or identical-simulator benchmark. The local
benchmark should be used to choose settings.
