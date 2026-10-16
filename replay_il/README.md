# Fresh replay imitation experiment

Extract this source update into **E:\Downloads\Chat_GPT_AI**, keeping your
existing `.venv`, replays, models and other runs. Run **REPLAY_IL_START.bat**.
It first checks dependencies and replay counts, prepares/resumes its dataset,
then starts or resumes the separate `replay_scratch01` experiment.
If dependencies are missing, run **REPLAY_IL_SETUP.bat** once and try again.

This implementation starts with **random weights**. With a 256-token vocabulary
it has **3,271,683 parameters, all trainable**. It loads neither 271 nor Nexto
weights. Existing bots and their weights are untouched. The project’s normalized
observation format is reused; this includes the ball, up to six cars, boost pads
and previous controls. Using a format does not load the model that first used it.

## Your replay folders and downloads

The defaults are your existing `data/replays/ranked-duels` and the new
`data/replays/ranked-doubles`. Your folder was described as GC3–SSL; files without
rank metadata retain **user-curated / unverified ranks** provenance.

**REPLAY_IL_DOWNLOAD_DUOS.bat** requests your Ballchasing token privately on your
PC, or uses `BALLCHASING_TOKEN` / `BALLCHASING_API_KEY`. It downloads at most 100
new doubles replays per launch, with resume, throttling and a 180-attempt hourly
ceiling. It uses the documented broad Grand Champion API search, then accepts
only matches where **all four players** have GC3/SSL metadata (tiers 21–22).
Missing ranks are rejected. This implements the intended quality filter from
your website link; it does not pretend that website numeric filters are API
parameters. Re-run to fetch another bounded batch. Keep API tokens out of chat,
source files and model configuration. Downloads are separate from training.

The importer supports 1v1, 2v2 and 3v3 state layouts. That does not mean a model
trained only on duels has learned team play: `manifest.json` reports actual
match counts by format and split. No 3v3 training is claimed without 3v3 replays.

## What the learning actually does

1. Parse real `.replay` files with RLGym Tools/Carball. Infer missing aerial
   controls; optionally refine pitch/yaw/roll against the observed next state.
   Simulate each transition and reject stale, invalid or poorly reconstructed
   motion. Position, velocity and rotation fit limits are pinned in the dataset.
   Reconstruction is approximate, not recovery of authentic controller hardware.
2. Reconstruct 120 Hz controls and sample causal state histories at 15 Hz.
   Each example contains eight past/current observations and the following
   **32 physics ticks** of controls (about 0.267 seconds). No future outcome is
   included in the observation. Button edges are retained at 120 Hz.
3. Fit up to 256 chunk medoids **on training matches only**. Every token decodes
   to an actual feasible chunk; jump/boost/powerslide never become fractional.
   Common controls and diverse rarer chunks seed the vocabulary. Reconstruction
   error is reported rather than hidden.
4. Train token cross-entropy plus three bootstrapped value heads from replay
   outcomes. The value target is the next goal’s signed result, discounted by
   time to that goal. It is a supervised label, not an RL reward. Random
   initialization includes the spatial encoder; its gradients are checked.
5. Save complete model/optimizer/RNG checkpoints. Keep the checkpoint with the
   best validation `token CE + value MSE`, and stop after four stale epochs.
   All players and clips from the same match stay in one 80/10/10 split. Replay
   IDs are deduplicated; when an internal match ID is absent, file SHA is the
   fallback, which cannot identify every alternate POV of the same match.

**There is no PPO, reinforcement-learning update, self-play, teacher policy, or
generated training match.** RocketSim during preparation verifies replay
reconstruction. Simulation during optional planning is inference only.

Cached shards make parsing resumable. A completed dataset is immutable: to add
new downloads, use a new `--dataset` directory and a new training run. Sampling
is capped fairly per replay so the global sample limit does not silently train
only on the first few hundred of 3,000 files. Raw histories can still take several
GB. Parsing 3,000 replays is substantial work; progress and rejection counts print
throughout, and errors remain in `parse_progress.json`.

## W&B and local proof of optimization

The default W&B project is **slater-replay-imitation**. Existing W&B login is
reused; **REPLAY_IL_WANDB_LOGIN.bat** signs in locally. Without usable online
authentication, the SDK records offline or the local JSONL log remains active.
The console and `wandb_state.json` show the actual mode and online URL when
available. API keys are never stored in the training protocol or ZIP.

Graphs include policy CE, value loss, gradient norms, validation token accuracy,
value MSE versus a constant-zero predictor, control reconstruction error and
parameter-change L2. Model weights and raw replays are not uploaded as artifacts.
Every event is also kept in `events.jsonl`; missing metrics stay missing.
Offline W&B runs can be synced with the SDK’s `wandb sync <offline-run-directory>`.

`model.json` records initialization and parameter counts. Each epoch records
actual optimizer updates and nonzero weight changes, with `rl_updates=0` and
`self_play_games=0`. A decreasing training loss alone is not reported as better
gameplay. Selection is explicitly **OFFLINE_VALIDATION_ONLY**; it never changes
the bot currently used by your extension.

## Pause, resume and held-out test

**REPLAY_IL_PAUSE.bat** requests a safe pause. Preparation finishes the current
replay. Training saves complete state after its current minibatch/validation.
Run START again to resume. A paused partial epoch is restarted from its beginning
with the saved optimizer; repeated examples are reported. Resume restores CPU
RNG; uninterrupted CUDA trajectories are not guaranteed bit-identical.

**REPLAY_IL_TEST.bat** evaluates the selected model on the untouched test matches.
The result is cached for that checkpoint. It refuses to reuse that test report
to tune successive checkpoints. Even good held-out imitation accuracy needs a
separate gameplay benchmark before competitive improvement can be claimed.

```bat
.venv\Scripts\python.exe -m replay_il run
.venv\Scripts\python.exe -m replay_il status
.venv\Scripts\python.exe -m replay_il run --run replay_duos02 --dataset data\isolated\replay_imitation\dataset02
.venv\Scripts\python.exe -m replay_il resume --epochs 10 --wandb-mode offline
```

## Candidate planner and kickoff book

**REPLAY_IL_PLANNER_BENCHMARK.bat** loads the new checkpoint and measures a
64-candidate, one-second RocketSim search on a private arena. Candidate continuations
are generated by the chunk policy, with batched inference. Ranking uses predicted
value, value-head disagreement and the policy prior. Only the first eight ticks
are intended for execution before replanning. The real world is never mutated.

Opponent controls in this prototype are held at their last observed value:
future human actions are unknown. Learned value can be wrong on states outside
the replay distribution; disagreement/prior penalties do not eliminate that
problem. The report measures actual latency instead of promising real-time play.
The cloud CPU smoke check completed 64 one-second candidates in about **1.29 s**
with a randomly initialized test model. This verifies execution, not playing
strength, and is too slow for 15 decisions/second on that CPU. Measure your own
hardware with the benchmark before integrating this search into a live bot.
This is an **offline planner prototype**, not an installed live browser/Roblox
controller. The new model format is **not a drop-in Nexto checkpoint**. Connecting
it to the game is a separate deployment step after real-data quality/latency checks.

A kickoff book stores verified training-clip first-touch controls from matching
spawn positions. Only observed first-touch entries are eligible; absent entries
stay absent. The helper requires an explicit kickoff signal, a centered stationary
ball, a matching spawn and teammate priority. It is not yet wired into the old
extension or advertised as a learned mechanic.

## TAS

Your TAS folder defaults to **E:\Downloads\Chat_GPT_AI\data\tas**. Run
**REPLAY_IL_TAS_AUDIT.bat** for a non-destructive audit. It saves
`data/isolated/replay_imitation/tas_audit.json`, including every clip's starting
car/ball poses, control lengths, checksums and missing verification metadata.
On the uploaded archive, 66 of 67 files decode (one is empty), totaling 108,461
input frames. Only **three** decoded clips start with the ball near center;
assuming every TAS starts from the center would create incorrect training data.

TAS can supply mechanic demonstrations when exact starting state, control mapping,
tick timing, boost/jump state and simulator compatibility are verified. It should
be a separately tagged, capped data source, with entire clips split as groups.
Mechanic-only TAS has no reliable match-outcome target: it must not be given
invented positive value labels. This release admits **real replay files only**;
it does not silently turn the uploaded legacy `.data` recordings into training
data. The project’s existing aligned-capture tools can be used to validate a TAS
source before an importer is enabled.

## Cloud validation and limits

Tests exercise actual RocketSim reconstruction, rejection of corrupted motion,
future-label exclusion, token feasibility, real supervised weight/optimizer
updates, checkpoint/resume, split isolation, private-world planning and strict
API filtering. Physics fixtures are explicitly test data, not GC3/pro replays.
The user’s Windows replay folder and API credentials are unavailable in cloud;
no trained pro-replay model, rank, live-game strength or W&B online run is claimed.

```sh
.venv/bin/python -m pytest -q tests/test_replay_imitation.py
```
