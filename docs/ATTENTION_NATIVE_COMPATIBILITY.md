# Preserving the capable attention policy in native training

The existing attention actor can run and receive gradients in C++ without being
distilled into the weaker MLP. An isolated LibTorch probe demonstrated this on
2026-10-13 using the protected original Nexto actor. Full native attention PPO
training remains implementation work. The actual Windows update180 checkpoint
was unavailable in the cloud, so the new local probe explicitly tests that file.

## What was verified

The actor contains **44 parameter tensors, 444,032 parameters**, and returns 90
action logits. Its forward input is `(query, entities, mask)` with shapes
`B×1×32`, `B×N×24`, and `B×N`. It is trainable TorchScript; its parameters have
not been replaced by inference-only constants.

The C++20 probe loaded the same exported actor as Python and produced identical
logits: **maximum absolute error 0** across 36 padded car views covering all nine
team sizes from 1v1 to 3v3, plus two unpadded duel views. A synthetic
cross-entropy loss produced finite gradients in **all 44 tensors**. One Adam
step changed all 44 actor tensors and changed its outputs, while a separate
frozen teacher remained bit-identical and received no gradients. Original
checkpoint files were preserved; optimization occurred only in memory.

This verifies native execution and autograd feasibility. It does not measure
soccer strength, PPO stability, or speed, and does not make the current native
GigaLearn MLP into an attention policy.

## A concrete observation hazard

The bundled traced attention **adds its mask to attention logits**. A positive
`1` is not a valid padding exclusion for this artifact: it increases attention
to a placeholder. `TeamObserver` returns boolean-style `0/1` markers, while
`slater_versatile_data.native_observation` converts positive markers to
`-10000`. Current `VersatileEnv` and its replay dataset already use the
conversion. Older direct `afk_team_research` actor calls pass the raw markers.

On the same duel state, merely padding from 37 to 41 entities with raw `0/1`
markers changed logits by about **3.98** in the packaged cloud probe. With the
correct additive mask, the difference was **5.72×10⁻⁶**. Permuting entities with
the matching mask changed logits by **1.53×10⁻⁵**, consistent with floating
point rounding. These are observation compatibility checks, not evidence of
team-playing skill. Kickoff randomization can change the exact reported
values; the packaged harness fixes its random seeds. These values are recorded
in `data/isolated/attention_native_probe/cloud_attention_probe01/report.json`.

Critic pooling should identify real entities with `mask == 0`. Using
`1 - mask` after additive-mask conversion incorrectly gives missing slots a
large positive weight.

## Run the local compatibility probe

Run `SLATER_22_ATTENTION_NATIVE_PROBE.bat` from the project. It initializes the
installed Visual Studio x64 compiler environment, exports a private copy of
the actual update180 actor, checks export weights exactly, generates current
observations, builds a standalone LibTorch executable, and checks C++ inference
and gradients. It does not modify the GigaLearn backend or any trainer and can
run while an unrelated training process continues. Compilation uses one job.
The current Torch installation, CMake, Ninja and Visual Studio toolchain are
required. CUDA-enabled Torch may require its matching toolkit for linking,
even though this probe executes on CPU.

To test another compatible attention checkpoint:

```bat
cd /d E:\Downloads\Chat_GPT_AI
SLATER_22_ATTENTION_NATIVE_PROBE.bat --source "E:\Downloads\Chat_GPT_AI\path\to\candidate.pt"
```

Results are under
`data\isolated\attention_native_probe\attention_probe_<timestamp>\report.json`;
the native process output is `cpp_probe.log` in that directory. A missing
update180 source is an error, not a silent fallback to original Nexto. Native
MLP `.lt` files are a different architecture and are not accepted here.

The Linux CPU build, original-Nexto fixtures and forward/gradient test were
actually executed in cloud. The Windows launcher and actual update180 still
require the local run above. The reported synthetic optimizer step is solely
a gradient test; its temporarily changed weights are not a playing candidate.

## What is compatible today

| Component | Existing behavior | Remaining work |
| --- | --- | --- |
| Attention actor | Trainable 444,032-parameter TorchScript; C++ forward and gradients work | Load the privately exported actual update180 in a native collector and PPO learner |
| Attention observations | Padded 41-entity Python builder handles 2–6 cars | Port the exact builder to C++ and establish state-to-input parity, not merely tensor-to-output parity |
| Team observation wrappers | `TeamObserver` handles 1–3 cars on either side; `NextoTeacher` wrapper restricts to 1v1 | Use the general wrapper and corrected additive mask for team matches |
| Native MLP observations | `PaddedObs` already has self, two teammate and three opponent slots with presence bits in 230 features | Current native launch path only spawns equal teams; asymmetric rosters require environment/collector validation |
| Native MLP action masks | Existing Python replica matches pinned native historical behavior | Preserve attention's actual 90-action inference behavior; extra native feasibility masks would change its policy |
| Replay bank | Current native binary bank allows only even total car counts and matched configured rosters | A new format is needed for arbitrary mixed rosters; do not reinterpret existing banks silently |
| Checkpoints | Attention `.pt` stores actor state with original architecture; native uses distinct `.lt` modules | Version architecture/observation/action/timing metadata and save actor, critic, optimizer and statistics atomically |

## Migration order that retains existing knowledge

1. Export a trainable attention module from the protected update180 state dict.
   Verify parameter names, shapes, values, forward outputs and actual gradients.
2. Implement native Nexto observations as three tensors or a documented packed
   buffer. Check Python versus C++ on grounded, airborne, jumped, flipped,
   demolished and boost-cooldown states, both colors and every roster size.
   Include nonzero previous actions, padding and car-order permutations.
3. Add a policy adapter in the native collector and PPO learner. The current
   MLP/shared-head construction is insufficient: the adapter must unpack the
   attention tensors in both action collection and minibatch optimization.
   Preserve action lookup ordering and the one-tick delay followed by seven
   ticks of new controls. Frozen rivals and teacher parameters must be excluded
   from optimizer updates and learner trajectories.
4. Keep independent environment trajectories and termination versus timeout
   bootstrapping correct. Add a compatible critic; a fresh critic is acceptable
   when disclosed, while the actor should retain update180 weights exactly.
   Match initial log probabilities, advantages and one tiny PPO step against
   Python before increasing throughput.
5. Benchmark identical weights, starts, team sizes, tick skip, action delay and
   sample budget. Only then compare fresh full matches and skill-retention
   tests. Train all learner-controlled teammates explicitly; spawning extra
   cars with a frozen policy is not equivalent to training coordinated teams.
6. Save pre-update and accepted candidates, frozen opponent versions and
   validation records. Do not replace the playing incumbent from reward or
   imitation loss alone. A candidate should pass fresh per-format matches and
   retention checks, including 1v1, 2v2, 3v3 and both directions of unequal teams.

C++/LibTorch is the shortest tested migration path because this project already
builds that stack. A Rust backend can also be evaluated, but switching language
does not remove the observation, policy, collector and checkpoint contracts.
No Rust training implementation was tested in this audit.

## How to judge a 30-million-steps-per-second claim

A speed number is not comparable until its unit and workload are specified.
Request the repository and exact commit, executable command, hardware, CPU
threads, GPU, environment count, roster sizes, tick skip, action delay, network
architecture, batch sizes, and timing interval. Distinguish:

- **Physics ticks:** arena simulation updates, possibly with no model inference.
- **Environment decisions:** one action-repeat block per arena.
- **Agent transitions:** one collected decision per controlled car; more cars
  can multiply this numerator without increasing arena throughput.
- **Collected learner samples:** transitions retained after excluding frozen
  rivals and scripted/off-policy actions.
- **End-to-end training samples:** useful learner transitions divided by wall
  time including inference, observation construction, optimization, resets,
  imitation refreshes and required evaluation.

At tick skip 8, 30 million arena physics ticks per second would correspond to
3.75 million arena decision blocks per second before counting controlled cars.
Thirty million per-player physics ticks is a different numerator. A tiny MLP or
physics-only benchmark is not an attention-PPO benchmark. Include warmup,
several measured iterations, independent repeats, memory use and correctness
parity. The useful outcome is measured strength gained per wall-clock hour
with the protected baseline retained.

## Source references

- [Exact attention observation builder](../vendor/nexto/nexto_obs.py)
- [Original actor action lookup](../vendor/nexto/original_agent.py)
- [General team observation and match implementation](../afk_team_research.py)
- [Existing corrected attention mask and replay schema](../slater_versatile_data.py)
- [Current versatile attention environment](../slater_versatile_env.py)
- [Native padded observations](../GigaLearn_Project/Native_Backend/PaddedObs.h)
- [Current native MLP construction](../GigaLearn_Project/Native_Backend/NativeMain.cpp)
- [Reproducible Python harness](../slater_attention_native_probe.py)
- [Standalone C++ probe](../GigaLearn_Project/Native_Backend/attention_probe/AttentionProbe.cpp)
