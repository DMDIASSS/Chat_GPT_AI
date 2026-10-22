# Replay RVQ: learned action chunks, state-only policy and all-car search

This is a **separate new experiment**, informed by the RocketLM discussion you
supplied. It reuses your existing prepared human replay shards. It does not
change `replay_scratch01`, `replay_mixed3v3_02`, their dictionaries, their resume
protocols or the original `replay_il` source. No old 271/Nexto weights are loaded.

The new production architecture has **3,074,595 total parameters**, including
the learned codec. Its codec is trained first, then frozen during policy
training. This is our implementation of the reported design, not the author's
code or a claim of matching their strength.

## What changed

| Original replay path | New RVQ path |
|---|---|
| 256 fixed medoid chunks | Learned VQ-VAE with four residual codebooks, 64 codes each |
| Eight-frame temporal policy | Current-state spatial policy |
| One categorical chunk label | Four code levels predicted sequentially, conditioned on previous levels |
| Fixed chunk controls | Learned decoded chunk plus an analogue offset bounded to 0.05 |
| Existing RLBot export uses direct policy only | New export includes optional value-guided RocketSim search |
| Old forecasts hold other cars' last inputs | New forecasts recompute every car's argmax policy each chunk |

Actions are still 32-by-8 arrays: throttle, steer, pitch, yaw, roll, jump, boost,
handbrake. Buttons are explicitly decoded to 0/1. The learned offset modifies
only analogue controls. Training uses a weighted button loss, emphasizing rare
jump presses and the executed first eight ticks. It never forces buttons during
play to imitate an improvement.

The codec fits on training matches. Decision thresholds for its button logits
are calibrated on validation prefixes, then frozen. The calibration report
clearly identifies that split; those fitted validation scores are not independent
test or gameplay results. The held-out test split is not scored by this workflow.

The new state policy masks the old query's eight previous-control slots during
both training and inference. Live packets do not provide other players' actual
buttons; this prevents the opponent predictor relying on replay-only inputs that
would be replaced by zeros in the real game. Physics and availability flags are
retained. The stored original observations are unchanged.

Training remains **100% supervised on cached human demonstrations and outcomes**.
No RL, self-play, generated training matches, search labels or online adaptation.

## Install and start

Extract the source update into **E:\Downloads\Chat_GPT_AI**, replacing included
source files. Preserve `.venv` and all of `data`. Training uses the dependencies
already needed by the original replay pipeline.

In CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_RVQ.bat start --device cuda
```

Default batch size is 128. Close Rocket League while training to free resources
on the 4 GB GPU. If a smaller batch is needed, choose it on the first launch,
e.g. `--batch-size 64`, and keep that setting for resume.

The default data source is the existing completed
`data\isolated\replay_imitation\dataset_mixed3v3_02`. If it is absent, the first
launch uses `dataset01`. The chosen path is then frozen in the new run. You can
explicitly choose an existing prepared dataset with `--dataset`.

**No replay parser is invoked.** Missing/corrupted completed shards cause an
error. They are not silently replaced with generated data. All supported modes
already present in the dataset participate; there is no mandatory 3v3 quota.

The new run is:

```text
data\isolated\replay_imitation\rvq_runs\replay_rvq01\
```

Stages:

1. Train the action codec, default total target 15 epochs, with validation-based
   selection and early stopping after four stale complete epochs.
2. Calibrate its button thresholds using validation samples. Preserve this small
   `button_calibration.json` sidecar; the selected codec checkpoint is unchanged.
3. Freeze the selected codec and encode four-code labels into the **new run's**
   `labels` folder. Original shards and token caches are untouched.
4. Train the current-state autoregressive policy, bounded analogue offset and
   three supervised value heads, default total target 15 epochs.

Codec training reads only the control arrays, avoiding unnecessary observation
decompression and GPU transfers. Policy training reads the last observation
frame from the stored causal history. Existing histories are not stitched into
invented long sequences.

The codec must improve over initialization and use more than a single constant
code pattern before policy training starts. Export through the launcher refuses
a policy that never improved over its initial validation baseline. These gates
catch basic failures; passing them does not prove a strong bot.

## Pause, resume and inspect actual learning

From a second CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_RVQ.bat pause
```

Wait for the training window to save its current stage and return before closing
it. Resume with the same start command. The pause flag applies only to this RVQ
run, not your original trainer or dataset. An interrupted partial epoch can
repeat examples on resume; model/optimizer/RNG state are saved at the checkpoint
boundary. Force-closing can lose updates since the last checkpoint.

```bat
REPLAY_RVQ.bat status
```

The targets are **total epochs**, not extra epochs each launch. To extend policy
training, if it has not early-stopped:

```bat
REPLAY_RVQ.bat start --device cuda --policy-epochs 25
```

Once policy training exists, its codec and calibration are immutable. Increasing
the codec budget then requires a new `--run`, since changing the codes would
change every policy target. Do not bypass the identity guards. Existing runs
remain resumable with their matching code, dataset, runtime versions and settings.

Useful files under the RVQ run:

| File/folder | Meaning |
|---|---|
| `protocol.json`, `dataset.json` | Source/data/settings identity and frozen dataset location |
| `training_control_sample.json` | Training-only button prevalence sample and bounded positive weights |
| `codec\model.json`, `policy\model.json` | Actual total/trainable parameter counts |
| `codec\best.pt`, `policy\best.pt` | Validation-selected stage models |
| `codec\latest.pt`, `policy\latest.pt` | Full stage resume checkpoints, including optimizer/RNG |
| `codec\button_calibration.json` | Frozen validation-fitted thresholds and before/after button metrics |
| Each stage's `selected.json`, `epoch_*.json` | Selection, prefix error, precision/recall, code usage or policy/value accuracy |
| Each stage's `events.jsonl`, `wandb_state.json` | Actual updates and W&B status |
| `status.json` | Latest saved stage progress, not proof a process is currently running |

The command log is `data\isolated\replay_imitation\rvq_launcher.log`. W&B uses
the existing local login and project `slater-replay-rvq`. No API key goes in a
command, source file or chat. `--wandb-mode offline` or `disabled` is available.

## Benchmark the trained search before choosing the live budget

After a selected policy exists:

```bat
REPLAY_RVQ.bat benchmark --device cpu --candidates 4 16 64 --repeats 5
```

Use the device that the actual RLBot interpreter will use. CUDA in the training
environment does not mean RLBot has a CUDA Torch build. The report is
`search_benchmark.json` under the RVQ run.

The search creates up to 64 lines using the top 16 first-level codes times the
top four conditional second-level codes, with argmax for the remaining two
levels. This is our explicit proposal construction. Each line simulates four
32-tick chunks, **128 ticks / 1.067 seconds**. All cars use the same frozen
replay-trained policy for their subsequent actions. Only the controlled car's
first chunk differs between proposals. The value-head mean scores the endpoint;
terminal goals use the known signed outcome. There is no hand-made movement,
mechanic-complexity or ball-distance reward.

The bot executes only the first eight ticks of the chosen chunk, then replans.
Other players are forecasts from the learned policy, not their actual future
inputs. This assumption can be wrong against unusual opponents. No online
opponent adapter is included.

## Export and use in RLBot v4

After training and checking reports:

```bat
REPLAY_RVQ.bat export --name ReplayRVQ01
```

Load:

```text
E:\Downloads\Chat_GPT_AI\data\rlbot_exports\ReplayRVQ01\bot.cfg
```

The export is self-contained. It includes a frozen inference graph, runtime
source, dependency requirements pinned to the training simulator versions, and
an integrity manifest. It does not require the training project after export.
RLBot's Python must install the listed dependencies, including RLGym/RocketSim
for search. A missing dependency or startup failure needs its actual error;
no successful live-game test has been performed in this cloud environment.

`runtime.json` defaults:

```json
{
  "device": "auto",
  "mode": "search",
  "candidates": 16,
  "adaptive": true,
  "scripted_kickoff": true
}
```

Adaptive search starts at four candidates, reduces after slow decisions and
grows only after repeated fast decisions, up to the configured maximum. This is
a **soft** latency response, not a guaranteed real-time deadline. A slow search
can still delay controls. Do not force 64 because another desktop reportedly
handled it. `mode: "policy"` provides a direct-policy comparison, with no search.

The kickoff is the existing basic scripted assist, clearly separate from the
network. No trained pro kickoff book is claimed. New exports preserve existing
folders; choose another name to export changed weights.

`RVQ_DIAGNOSTICS.json` in the export records learned/search/kickoff button counts,
latencies, over-budget decisions, selected value/codes and the actual candidate
budget. When several cars share a folder it contains the latest writer's record,
identified by `car_index`. It is not a merged team statistic.

## What was actually verified, and what remains unknown

The test suite exercises learned codebook gradients, exact 0/1 outputs, conditional
code prediction, dynamic-batch TorchScript parity, both optimizer stages,
safe pause/resume, cached-data preservation, canonical features for both teams
in 1v1/2v2/3v3, physical forecast-state construction, all-car rollout decisions,
and a self-contained search export in a separate interpreter. The RLBot external
interface is stubbed there; RocketSim is real. This is not a real game or evidence
of playing strength. No CUDA hardware is available in this cloud.

A diagnostic using one of your actual human replays produced 1,024 verified
chunks. The original full-chunk medoid assignment missed 63 of 155 jump-held
ticks in the executed prefix. Prefix-only nearest-medoid assignment reduced
that to 20, with nine false-positive ticks. That identifies a representation
tradeoff, not a complete explanation of live behavior.

A small learned-codec probe reduced prefix reconstruction MSE on another subset
of the same replay from approximately 0.104 for the old dictionary to 0.082.
Button F1 was mixed; the new codec was not uniformly better. That probe used a
correlated within-replay split, **not independent-match validation**. Production
training/calibration uses the existing whole-match splits. No private weights or
raw replay samples from that probe are included in the source update.

On this cloud CPU, with the full-size **untrained engineering model**, two Torch
threads and five warmed 1v1 kickoff repeats:

| Candidates | Median ms | p95 ms |
|---:|---:|---:|
| 4 | 30.10 | 49.13 |
| 16 | 132.51 | 154.88 |
| 64 | 228.74 | 275.71 |

These are architecture timing checks, not your GTX 1650/i5 measurements, live
match tail latency or trained-model strength. Timing varied considerably between
cloud runs; a previous check put 16 candidates near 59 ms. A fixed 16-candidate
deadline is therefore not established here. The reference implementation still
has substantial all-car simulation/network cost. It does not reproduce the
author's claimed 50–60 ms / 64-candidate desktop result.

Additional limits:

- Live jump/flip/held-input, demolition and boost-pad respawn timers are estimates.
- Standard Soccar only. Known packet hitbox dimensions map to standard simulator
  bodies; when dimensions are absent, Octane is assumed and recorded as a limit.
- Your cached observation contract lacks match clock and score features. This
  update does not invent them or claim the author's full context representation.
- Value targets reuse the existing cached next-goal labels; missing/truncated
  outcome semantics remain worth auditing. Check value MSE against constant zero.
- Learned code combinations and policy mistakes can enter states outside the
  replay distribution. More candidates or epochs do not automatically fix that.
- The prepared dataset may still contain no accepted 3v3 samples despite 3v3
  files being present. Parser failures are not fixed by a different model.

Use the selected codec/policy reports and the trained search benchmark before
judging the result. The old model is preserved for comparisons. Nothing here
claims RocketLM's reported wins, mechanics or training time have been reproduced.
