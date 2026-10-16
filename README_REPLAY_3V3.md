# Offline imitation with the curated 3v3 group

For the consolidated start/pause/status/results workflow and fixed total-epoch
resume semantics, use [REPLAY_FINAL_GUIDE.md](REPLAY_FINAL_GUIDE.md) and
`REPLAY_IL_FINAL.bat`. The original launchers below remain available for compatibility.

Extract this update into `E:\Downloads\Chat_GPT_AI`, replacing the included source
files. Keep the existing `.venv` and private data. Run in CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
DOWNLOAD_3V3_GROUP.bat
REPLAY_IL_START_3V3.bat
```

Run the training command after downloads finish. Acquisition and training are
separate; neither launches a game or self-play. The downloader defaults to:

https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f

It reuses the same saved local Ballchasing token as the doubles downloader, or
the `BALLCHASING_TOKEN` / `BALLCHASING_API_KEY` environment variable. If missing,
it asks in the local console with hidden input and saves it in ignored private
data. Do not send the token in chat. Token configuration remains available via
`CONFIGURE_BALLCHASING_TOKEN.bat`.

The group API query stays scoped to this group while following pages. Only
ranked-standard metadata with three players on each team is accepted. Existing
replay IDs and identical content are skipped across `data/replays`; completed
files are never overwritten. Rerunning resumes pending downloads after a
failure or Ctrl+C. API/local cooldowns persist across restarts. When the report
says `RETRY_LATER`, rerun after the recorded cooldown. `--refresh` revisits the
newest listing without redownloading existing content. Group subgroups are not
recursively enumerated by this version.

The group is user-curated. This environment could not access Ballchasing to
independently inspect its contents; authenticated end-to-end downloading must
run on your PC. The downloader records supplied player ranks and car IDs/names,
and does not turn missing metadata into verified GC3/SSL or Octane hitboxes.
API pagination, scope, retries, duplicate detection and provenance are covered
by local response-fixture tests.

## Separate training run

The training launcher uses:

* Inputs: `data/replays/ranked-duels`, `ranked-doubles` and `ranked-standard`.
* New immutable dataset: `data/isolated/replay_imitation/dataset_mixed3v3_02`.
* New random-initialized run: `data/isolated/replay_imitation/runs/replay_mixed3v3_02`.

It first prepares or resumes reconstruction, then reads the accepted shards and
requires at least two actual 3v3 matches in each train/validation/test split.
It writes `format_audit.json` with real sample and match counts. If 3v3 parsing
produces no useful chunks or lacks a split, training stops with the evidence
preserved. A folder full of replay files is not reported as learned team play.
If coverage fails, inspect `parse_progress.json`; add suitable replays and use a
new dataset name after a completed immutable dataset has been built.

Then it starts the existing supervised trainer with W&B support. A rerun resumes
the same new experiment. The completed `replay_scratch01` run is not overwritten
or used as pretrained weights. This default creates a fresh mixed-data model,
not a warm start of the completed duels/doubles model. The training and parser
source files are unchanged, preserving existing resume fingerprints.

For custom names/budgets, pass the existing trainer arguments:

```bat
REPLAY_IL_START_3V3.bat --run replay_mixed3v3_03 --dataset data\isolated\replay_imitation\dataset_mixed3v3_03 --max-replays 3000 --max-samples 500000 --epochs 10 --device cuda
REPLAY_IL_PAUSE_3V3.bat
```

For custom names, pass the same `--run` and `--dataset` to the pause launcher.
Preparation finishes its current replay; training saves at a safe boundary.
Reconstruction can take substantial time and its controls remain estimates.
No fit threshold was loosened to make more samples pass.

## What the model learns

The existing 3,271,683-parameter model observes eight past/current states and
predicts a token representing the next 32 physics ticks of controls. A 256-entry
vocabulary is fitted on training matches only. It is a dictionary of real short
control chunks, not named tricks or text words. Repeated predictions combine
chunks as observed situations change. Three supervised heads predict a
discounted next-goal result; no hand-written movement reward or RL update is
introduced.

Training is entirely offline. Candidate forecasting is optional inference and
latency benchmarking; its snapshots are never fed back as training demonstrations.
Do not interpret lower imitation loss as proven competitive strength. Use
validation metrics for selection and keep the held-out test untouched until
the final chosen checkpoint. A complete model of the community post's claimed
strength cannot be guaranteed by matching its parameter count.

The separate [runtime tuner](README_REPLAY_TURBO.md) can later benchmark the new
selected checkpoint with `--run replay_mixed3v3_02`. It does not start a game.
See [the continuation brief](HANDOFF_OFFLINE_IMITATION.md) for the full current
state, constraints and links.
