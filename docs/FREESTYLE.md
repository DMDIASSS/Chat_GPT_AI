# Freestyle: a separate model trained from scratch

Freestyle uses pinned GigaLearn C++ PPO, RocketSim physics and LibTorch. Its
policy and critic start with random weights; none of update180, update271 or
the existing attention checkpoints supplies its initialization. Runs live in
`data/isolated/freestyle/runs/`. The current playing bots remain separate.

## Windows: start here

1. Extract the source update directly into `E:\Downloads\Chat_GPT_AI`, alongside
   the existing `.venv` and `data` folders.
2. Connect the charger. Pause other trainers before building or training to
   give this experiment the laptop's CPU, RAM and GPU budget.
3. Run `FREESTYLE_SETUP.bat`. It installs the pinned build/monitoring helpers,
   reuses the existing Torch installation, builds a separate executable,
   runs a finite offline smoke test, then opens the Freestyle app.
4. In the app, leave run `freestyle01`, W&B `online`, and the supplied settings
   for the first experiment. Click **Start new**. If no local W&B login exists,
   a password dialog appears; paste your key with Ctrl+V. The key is handled by
   W&B's local login and never belongs in JSON settings or Git.
5. Click **W&B dashboard** after the online run starts. Use **Safe pause** to
   finish the current PPO update and save. Wait for `PAUSED`, then use **Resume**.

The command-line equivalents are:

```bat
cd /d E:\Downloads\Chat_GPT_AI
FREESTYLE_TRAIN.bat
FREESTYLE_PAUSE.bat
FREESTYLE_RESUME.bat
FREESTYLE_STATUS.bat
```

Run the pause command in a second window. `max_updates: 0` means train until
paused; it does not mean improvement will continue indefinitely. A positive
`--updates N` on train/resume gives that launch N additional updates. A fresh
run name is required for changed training settings. Resume uses the saved
settings, model, optimizer, normalization and curriculum state.

## What the model sees and learns

The separate 512-float observation includes normalized ball/car physics,
car-local geometry, prior controls, boost pads, resources, wall/goal distances,
curriculum context, short ballistic forecasts and slots for other cars. Optional
simulator contact evidence has a visibility mask and is hidden in a fraction
of episodes. A matching live observation adapter is still needed before an
RLBot export: the old Nexto attention exporter cannot load this architecture.

The default actor and critic each have three 768-unit hidden layers. Freestyle
has its own 94-action table, adding opposing yaw/roll plus jump controls for
stall attempts to the upstream 90 actions. This enables an input combination;
it does not certify that the model knows stalls. Four-tick
actions give 30 decisions per simulated second. CUDA performs neural-network
work; RocketSim physics remains on CPU. These settings are starting points for
the GTX 1650 4 GB / i5-10300H laptop, not a measured optimum. Reduce worlds or
minibatch size if memory becomes limiting.

The curriculum starts with solo contact/pop practice, then air carry, reset
acquisition, reset use and repeated resets. Later stages cover pinch, double-tap
and psycho proxies, recovery and walldash proxies. The starts vary with
difficulty and retain some foundation practice. Independent, deterministic
evaluation episodes use separate seeds; repeated successful evaluations raise
difficulty and then advance the stage. Low scores leave the stage in place.

The scripted goalie is absent from physical play during the initial solo
stages and activates from `reset_use` by default. Its actions never enter PPO
training rows. Change `defender_after_stage` or set `defender: "none"` before
starting a new run; `defender_strength` controls this simple goalie, which is
not Nexto or a measured competitive opponent.

**Mechanics catalogue** in the app lists 129 mechanics and aliases, including
the supplied flicks, reset variants, pinches, dashes and shots. Each entry says
whether its objective is implemented, approximate or still planned. Most named
variants need their own validated detector before adding specialized rewards.
The catalogue is not a claim that all 129 can already be trained independently.
See [FREESTYLE_MECHANICS.json](../FREESTYLE_MECHANICS.json). Community names such
as Athena flick can denote a crossbar miss; they should not become success
rewards merely because they appear in a mechanics list.

Small approach, jump and touch rewards help a random policy begin learning.
Their weights taper as it advances. Stronger rewards require recent ball
contact, directional progress, a timed chain or an attributed finish. Each
component has an episode budget, with an overall positive-reward cap. Standing
near the ball, hovering beside it and repeating the same contact cannot earn
unbounded rewards. Goal rewards remain available from the beginning; a
qualified mechanic-to-goal sequence earns more.

Reset tracking runs at every 120 Hz physics tick, including ticks between policy
decisions. It requires wheel/contact geometry and a spent resource being
recharged away from an arena surface. A spawned available flip or leaving a
wall is not an earned ball reset. A later reset must be acquired and consumed
again. Pinch, double-tap, psycho and walldash detectors use geometric and
kinematic proxies; their success labels do not certify the complete named move.

## Graphs, checkpoints and recovery

W&B records PPO actor/critic losses, entropy, policy KL, learning rates,
throughput, raw and weighted reward contributions, event counts, curriculum
difficulty and independent evaluation success. Inspect reward components
alongside actual event counts and evaluation scores: a rising training reward
alone is insufficient evidence of better ball control.

The run folder contains:

- `protocol.json` and `config.json`: initialization, source/binary identity and
  immutable settings.
- `events.jsonl`: complete per-update metrics, retained even if W&B is offline.
- `progress.json`, `curriculum.json`, `latest.json`: current status and the most
  recent completed checkpoint.
- `checkpoints/<timesteps>/`: policy, critic, optimizers, normalization, RNG
  and curriculum state, plus a completion marker.
- `native_*.log`: native startup, PPO and error output.

Periodic snapshots are retained, as are the initial random checkpoint and
pause/finish checkpoints. Incomplete writes have no completion marker and are
excluded from resume. Power loss can discard work since the last completed
save. Physical episodes restart after resume; this is not a bit-for-bit
continuation of every arena trajectory. No checkpoints are automatically
deleted, so monitor disk space during a long run.

W&B reuses its locally configured key. Cancelling login allows offline training
under the default fallback setting. The native executable receives no W&B
credential. Offline sessions can be uploaded later using W&B's `sync` command;
the local event log remains the authoritative complete metric stream.

## Scope of this release

This is a working training experiment, not a trained freestyle champion.
Complex tricks can require substantial exploration and compute; a larger
network cannot guarantee them. Synthetic drill success needs visual and live
game validation before claiming practical mastery. See
[the source review](FREESTYLE_RESEARCH.md) for the upstream guidance, API details
and differences between this trainer and the older attention continuation.

Cloud validation compiled the final native backend and passed 38 focused
checks. Real finite CPU runs verified positive learner rewards, independent
evaluation, optimizer/curriculum resume, stable W&B offline run identity,
preserved initial weights, ignored incomplete newer checkpoints, safe pause
and active-goalie exclusion from PPO. Actual ball-wheel reset physics,
two-car ordering, 94 action masks and 240 randomized stage/color starts were
also checked. These small runs establish operation, not learned mastery.
Windows/CUDA execution and authenticated online W&B must be checked on the
PC; cloud validation used CPU and the real offline W&B SDK.

## Windows duplicate Learner linker error

If setup ends with `LNK2005` mentioning both `Learner.cpp.obj` and
`FreestyleLearner.cpp.obj`, install the current Freestyle source update and
rerun `FREESTYLE_SETUP.bat`. The fix normalizes Windows source paths and
requires exactly one upstream learner to be replaced before compiling. It
does not suppress linker errors or edit the pinned upstream checkout. Keep
the existing build directory so Ninja can reuse completed objects; reinstalling
Torch/CUDA or deleting checkpoints is unnecessary for this error.

The fix adds five CMake regression cases for backslashes, case differences,
relative paths and invalid source counts. All 43 focused tests pass in cloud.
