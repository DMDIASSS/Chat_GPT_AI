# Offline replay bot: all formats, saved chunks and the final workflow

Extract this source update into **E:\Downloads\Chat_GPT_AI**, replacing the
included files. Preserve `.venv`, `data`, replays, shards, checkpoints and tokens.
This update does not overwrite the fingerprinted `replay_il` training code.
Training remains supervised replay imitation: no RL, self-play, teacher-generated
training games or reward shaping. Short physics checks reconstruct demonstrations;
they are not policy training matches.

**All-format update:** `REPLAY_IL_FINAL.bat start --device cuda` now accepts
1v1, 2v2 and 3v3 by default. Missing 3v3 data no longer blocks your accepted
duels/doubles data. The existing `replay_mixed3v3_02` / `dataset_mixed3v3_02`
names are retained to reuse saved work; the name does not restrict the format.
If your last launch finished parsing and stopped at the 3v3 audit, run the same
start command again. It verifies and reuses the completed dataset without
reconstructing those replays again. To check without starting training:

```bat
REPLAY_IL_FINAL.bat cache
```

`CACHE_VERIFIED` prints the actual hash-verified shard and saved sample counts.
The `.npz` shards are saved reconstructed chunks/observations; `tokens.npy` is the
action dictionary created later by training. A failure before training starts
does not mean your reconstructed chunks were lost. Preserve the whole dataset,
including `manifest.json`, `shards`, metadata and `input_snapshot.json`.

## 1. Repair the bot you already exported

Close RLBot first, then in CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_FINAL.bat repair --scripted-kickoff
```

This repairs `data\rlbot_exports\ReplayScratch01`, fixes boost-pad matching and
updates the wrapper integrity hashes while preserving `policy.pt` and `tokens.npy`.
The `--scripted-kickoff` flag enables a basic drive/steer/boost assist. It yields
to a closer teammate, stops after ball movement or three seconds, and gives
control back to the model. It is explicitly scripted, not a learned/pro kickoff.
Omit the flag to retain the existing kickoff setting. To turn it off later,
set `"scripted_kickoff": false` in that export's `runtime.json`.

Restart RLBot and select the same `ReplayScratch01\bot.cfg`. The console should
show `REPLAY_BOOST_MAP_READY`, `REPLAY_MODEL_READY`, then `REPLAY_OUTPUT` every
five game seconds. `source scripted_kickoff` identifies the assist; `source policy`
identifies model output. Your actual vocabulary's token 0 has zero throttle and
boost during its first eight ticks. A policy choosing it can stay stationary
without an input or startup failure. The patch does not secretly force throttle
during normal learned play.

## 2. Choose the correct existing run

The commands below default to the separate mixed-format run:

| Purpose | Run | Dataset |
|---|---|---|
| Completed earlier model | `replay_scratch01` | `data\isolated\replay_imitation\dataset01` |
| Current all-format model (legacy name retained) | `replay_mixed3v3_02` | `data\isolated\replay_imitation\dataset_mixed3v3_02` |

To inspect the model that already finished training:

```bat
REPLAY_IL_FINAL.bat results --run replay_scratch01
```

It is already trained. Do not start another run merely to export it. To export
that model into a new folder:

```bat
REPLAY_IL_FINAL.bat export --run replay_scratch01 --name ReplayScratchFinal --scripted-kickoff
```

For custom run names/datasets, use the same `--run` and `--dataset` arguments on
start, status, pause, results, analysis and test. The default dataset for custom
names remains the mixed dataset unless explicitly overridden.

## 3. Collect the intended replay batch before creating a new dataset

Existing completed datasets do not need to be downloaded or parsed again.
For a **new** dataset, the final workflow recursively discovers `.replay` files
anywhere under `data\replays`, including custom subfolders, without filtering out
1v1 or 2v2. By default it selects all discovered files up to the parser's
100,000-file safety limit. `--max-replays` is an explicit optional smaller limit;
there is no default 3,000-file selection limit in this workflow now. The default
sample budget is at least 500,000 and grows when needed to cover a large input
list. An explicit budget too small to cover every selected replay is rejected.
The sample budget and per-match sampling still limit the saved chunks, not their
quality thresholds. Validation/test matches remain excluded from optimization.

The curated 3v3 downloader is optional:

```bat
DOWNLOAD_3V3_GROUP.bat
```

The group defaults to:
https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f

It reuses your saved local Ballchasing token and skips existing IDs/content.
If it says `RETRY_LATER`, wait for the saved API cooldown, then rerun it. The
cloud cannot authenticate to your private token; live downloading occurs on
your PC. Group quality and Octane-hitbox claims are user-curated provenance until
independently verified from the actual replays. Missing ranks are not invented.

Malformed/unsupported replays and chunks that fail reconstruction are reported
and excluded, rather than being silently treated as usable demonstrations.
In particular, a BoxCars `MissingAttribute` parsing failure needs reader support
for that replay protocol; removing the format gate does not decode those files.

Use a defined downloaded batch for each dataset. New downloads after parsing
starts belong in a future dataset; do not keep changing an experiment's inputs.

## 4. Parse and train with one command

Close the game to free GPU resources, then:

```bat
REPLAY_IL_FINAL.bat start --device cuda
```

The stages are:

1. **PREPARING_REPLAYS:** freeze a replay input list in `input_snapshot.json`,
   reconstruct inputs, verify physics, and reuse valid completed shards.
2. **VERIFYING_DATASET:** verify saved shard hashes, independent match splits and
   the actual accepted 1v1/2v2/3v3 sample counts. There is no mandatory 3v3 quota.
   A replay folder count does not prove useful samples were produced.
3. **STARTING_FRESH_TRAINING** or **RESUMING_TRAINING:** invoke the existing supervised
   trainer, preserving model/optimizer state on resume.
4. **TRAINING_BUDGET_COMPLETE** or **EARLY_STOPPED:** report the selected model and stop.

The first fresh launch creates `replay_mixed3v3_02` with random weights. A later
launch of the same run resumes it. `--epochs 10` is now a **total saved-epoch
target**, not ten extra epochs every time you launch. A completed run is not
trained again on rerun. Four stale validation epochs also stop it. This behavior
belongs to `REPLAY_IL_FINAL.bat`; older launchers keep their old semantics.

Every 30 seconds a heartbeat prints the last durable parser/training information.
An unchanged update can mean initialization, vocabulary fitting or validation;
it is not automatically a crash. Actual per-batch records are in `events.jsonl`.
W&B remains supported; the logged `wandb_state.json` shows online/offline status.

If preparation reports many rejected replays or no contiguous chunks, inspect
`parse_progress.json`. Rerunning the same bad data does not make its controls
correct. Do not loosen fit thresholds or erase cached evidence just to obtain
more samples. `format_audit.json` reports what actually survived parsing. A
duels/doubles-only dataset is valid and is not advertised as learned 3v3 play.
Use the optional `--require-3v3` flag only when you deliberately want at least two
accepted 3v3 matches in each split. The old `REPLAY_IL_START_3V3.bat` remains
strict for compatibility; use `REPLAY_IL_FINAL.bat` for these all-format defaults.

## 5. Pause and resume without confusing cached work with lost progress

Open a **second CMD** in the project folder:

```bat
REPLAY_IL_FINAL.bat pause
```

Wait for the first window to finish its current replay or training checkpoint
boundary and return an exit code before closing it. Validation and W&B shutdown
can take time. Do not delete `.npz`, `.pt`, `tokens.npy` or protocol files.

Resume using the same start command:

```bat
REPLAY_IL_FINAL.bat start --device cuda
```

Parsing counters may start at 1 again while checking cached shards. Valid
completed replays are reused; the one interrupted before its shard was committed
may be reconstructed again. A safely paused partial training epoch resumes from
that epoch's start with saved model/optimizer state, so some examples repeat.
Force-closing CMD can lose work since the last checkpoint. Safe pause is the
preferred stop method; a forced interruption does not promise per-batch recovery.

The new workflow freezes its input list and replay/sample budgets to avoid a
fresh download changing the per-replay sampling cap during resume. For a partial
dataset originally started by a legacy launcher, existing shards are reused only
when their saved reconstruction configuration still matches. Source filenames,
inputs and budgets should remain stable.

Existing snapshots retain their original budgets automatically; this update
does not change old parser settings or invalidate cached shards. A completed
`manifest.json` takes priority over fresh discovery, so new files downloaded
later are not silently appended to an existing training experiment.

## 6. Tell a pause, an error and completion apart

```bat
REPLAY_IL_FINAL.bat status
REPLAY_IL_FINAL.bat results
```

These show saved progress and write `results_summary.json` for the results
command. Saved stage labels are not proof that a process is currently alive.

| Message | What to do |
|---|---|
| `PARSING_NOT_COMPLETE` / saved pause | Rerun the same `start`; valid cached work is reused. |
| `READY_TO_TRAIN` | `start` verifies the dataset and starts the trainer. |
| `CHECKPOINT_SAVED` | Inspect CMD/heartbeat; `start` resumes if the previous process has stopped. |
| `TRAINING_BUDGET_COMPLETE` | Read results, then export. No further training is required for that budget. |
| `EARLY_STOPPED` | Validation stopped improving; use `best.pt`. More repetitions are not automatically better. |
| `INSUFFICIENT_3V3_DATA` | Only enforced with `--require-3v3`. The default uses accepted 1v1/2v2/3v3 data without this quota. |
| Nonzero exit / `STOPPED_WITH_SAVED_PROGRESS` | Read the actual error in CMD/launcher.log. Preserve checkpoints/shards and resolve the cause. |
| Code/dataset/protocol mismatch | Restore the matching environment/source or use a new run; do not bypass identity guards. |

The result files live in:

```text
data\isolated\replay_imitation\runs\replay_mixed3v3_02\
```

Important files: `best.pt` + `tokens.npy` (selected model), `latest.pt` (resume
checkpoint), `selected.json` (validation metrics/hash), `progress.json`, epoch
reports, `events.jsonl`, `results_summary.json`, and `wandb_state.json`.

## 7. Check whether it learned useful prediction rather than a common token

```bat
REPLAY_IL_FINAL.bat analyze --device cuda
```

This evaluates up to 2,000 validation samples and writes `validation_diagnostics.json`.
It does not train, play matches or touch the held-out test. Read:

For jump/boost problems in the existing `ReplayDuelsDoubles` export, close RLBot
and run `CHECK_REPLAY_DUELS_DOUBLES.bat`. It repairs only the wrapper, compares
the exported model with the trained model on 512 cached validation inputs, and
reports reconstructed/tokenized/predicted button rates. After restarting RLBot,
the export also records continuous button counts and timing in
`CONTROL_DIAGNOSTICS.json`. See
[README_REPLAY_CONTROL_CHECK.md](README_REPLAY_CONTROL_CHECK.md). No replay
parsing, training or forced movement is performed by this check.

* Token top-1 accuracy **versus a constant predictor using the most common
  training token**. The report states whether all training label caches were
  available for that baseline. Similar numbers mean accuracy alone is weak
  evidence of conditional skill.
* Prediction counts and the largest single-token fraction. A dominant output
  can expose action collapse even when loss falls.
* Control reconstruction MSE and predicted/target no-throttle/boost fractions.
  Coasting and aerial control can legitimately have no throttle/boost; this is
  a diagnostic, not a movement penalty.
* Value MSE versus the constant-zero predictor. Rising training updates and
  nonzero weight changes prove optimization occurred; they do not prove strength.

Use validation for development. Only after selecting the final checkpoint, run
the held-out test once:

```bat
REPLAY_IL_FINAL.bat test
```

Its identity-cached report refuses reuse for a different checkpoint. Do not tune
successive models against that same held-out test.

## 8. Export the newly trained selected model

```bat
REPLAY_IL_FINAL.bat export --name ReplayMixedFinal --scripted-kickoff
```

Load this file with **RLBot v4 Add/Load Bot**:

```text
E:\Downloads\Chat_GPT_AI\data\rlbot_exports\ReplayMixedFinal\bot.cfg
```

Existing export folders are preserved; use another `--name` for changed weights.
The export is self-contained, retains eight-frame history and exact first-eight-
tick chunk controls, and uses direct policy inference. It does not include the
one-second RocketSim candidate-search planner. Playing with the exported bot is
deployment; those games are not fed back into training.

## What it would take to approach the community 3.3M-parameter claim

The earlier completed run used 279 replay inputs, not the claimed roughly 3,000.
It already has 3,271,683 parameters, but parameter count alone is not the recipe.
The current tokens are 32-tick control medoids, not text words or named mechanics.
Complex plays span multiple chunks; the model conditions on roughly half a
second of observations. Its old held-out top-1 was about 23.7%, top-5 55.2%, with
value MSE 0.2185 versus 0.2484 for constant zero. Those are offline accuracy
measurements, not proof of a strong playing bot.

The concrete next targets are:

1. Build a larger, diverse, high-quality **accepted** replay dataset. Count usable
   samples and formats, inspect reconstruction error and deduplicate whole games.
   Thousands of filenames with failed fits do not help. Keep the evaluation split
   independent and match data coverage to the intended mode.
2. Beat simple validation baselines and avoid a dominant idle token. More epochs
   cannot repair bad control labels, missing rare-mechanic coverage or a poorly
   represented action dictionary. Any weighting/tokenizer/model change needs a
   versioned new training experiment, not a hidden modification of this run.
3. Validate long control sequences and rollout values before claiming strong
   planning. The referenced bot reportedly uses 64 one-second forecasts and a
   pro kickoff book. Our latest measured four-worker 64-candidate path was about
   147 ms median / 150 ms p95 on your laptop, above the 66.7 ms decision interval.
   Sixteen candidates met the warmed benchmark interval; a running game adds
   contention. The new turbo/CUDA-graph tuner still needs local measurement.
4. A real replay-derived fast kickoff book remains missing in the supplied run.
   The optional basic scripted assist here is not such a book. Other players'
   future actions are also not learned by the current search; it holds their
   last observed controls. These are material differences from an ideal system.

Matching the community bot's strength cannot be guaranteed by changing one
setting or using 3.3M parameters. Its original implementation/results link was
not supplied, so the claim is not independently verified here. The entire
learning pipeline can remain offline while these data/model/inference gaps are
addressed; no RL or self-play is required by this update.

## What the supplied reference bots showed

The archives were read without executing supplied models/code. TensorBot's
config describes recorded-Diablo imitation; its wrapper uses 24 normalized inputs,
separate blue/orange models and a scripted kickoff. Omus contains an SB3 1.4-era
checkpoint and optimizer data, without an RLBot wrapper. These inform packaging
and diagnostics; their weights were not copied into your model. Neither archive
establishes the performance of the separate 3.3M-parameter community claim.
