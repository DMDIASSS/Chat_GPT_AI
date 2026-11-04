# Show progress and get a training review

The v1.3 exporter creates a small ZIP with charts, selected configuration, opponent/mechanics statistics, PPO metrics, checkpoint hashes and matching evaluation results. It reads your run without changing its settings.

## Update an existing install

1. Pause with **15_MIXED_PAUSE.bat** and wait for the trainer to save and exit.
2. Extract the v1.3 ZIP into `Chat_GPT_AI`, replacing the `NovaForge` source files. Keep `.venv`, `assets`, `datasets`, `models` and `runs`. No new dependencies are needed for reporting.
3. Run **1_CHECK.bat**. Resume with **18_START_OR_RESUME_WANDB.bat** when ready. Existing runs keep their configuration, weights, optimizer and W&B ID.

A new installation still starts with **0_INSTALL.bat**, checks/smoke, and the teacher/pretraining steps in [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md).

## Quick report to send in the chat

1. Run **19_EXPORT_PROGRESS_REPORT.bat**. Training may keep running for this step.
2. Find the printed file under `NovaForge\reports`, named like `diverse01_progress_...zip`.
3. Upload that ZIP here. Optionally add a short gameplay clip and describe a repeated problem: stalling, missing kickoffs, chasing, aerial misses or poor recovery.

Extract the small report ZIP and open **progress.html** in a browser to inspect it yourself. It works offline, with metric selectors and hover details. The bundled JSON/CSV files support a more detailed review. It includes only selected metrics/configuration and checkpoint hashes, without copying model weights, raw logs, replay files, W&B event files or credentials. It can contain the run name and an ordinary W&B dashboard URL; remove that URL from `report.json`/`progress.html` before sharing publicly if you prefer.

Reports are snapshots: an active run can move forward while files are read. A paused run gives a more consistent snapshot. Old logs cannot be recovered if a previous version overwrote them. Starting with v1.3, resuming archives the previous PPO CSV before opening a new one.

## Stronger evidence: compare saved checkpoints

1. Pause with **15** and wait for the save/exit.
2. Run **20_COMPARE_PROGRESS.bat**. It compares the earliest valid saved checkpoint with the current saved checkpoint, then automatically exports a progress ZIP.
3. Upload the newly printed ZIP. Resume with **18** afterward.

The default comparison runs Nexto, Ripple, Chronos and Galactus ports on kickoff starts: five seed pairs per opponent, both team sides, up to 20 simulated seconds per trial. That is **40 trials per checkpoint, 80 total**. It requires the downloaded teachers and at least two different saved checkpoints. Actual elapsed time depends on your PC. A file lock prevents this helper from comparing while the same run is training.

These are **first-goal simulator trials**, with timeouts counted separately. They are an early screen, not a full-match win rate or proof that one checkpoint is stronger. The report shows both checkpoints' scoring fractions, timeouts, the paired mean outcome change and its standard error. The standard error is a descriptive trial-level estimate; shared seeds can correlate trials. An all-timeout result is inconclusive. Use more trials, another held-out seed set, mechanics starts and actual offline RLBot games before deciding a change helped. Simulator ports have the limits described in [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md).

Manual commands from Command Prompt inside `NovaForge`:

```bat
.venv\Scripts\python.exe run.py report --run diverse01
.venv\Scripts\python.exe run.py compare-progress --run diverse01 --pairs 10 --seconds 30 --seed 920001
.venv\Scripts\python.exe run.py report --run diverse01
```

For a different run, replace `diverse01`. For a mechanics comparison, add `--scenarios shot,defense,dribble,aerial,recovery,wall`; this multiplies trial count and runtime. CLI comparisons save evaluation JSON; launcher 20 also performs the final export.

## What the report can tell us

The report separates score/concede/timeout fractions, ball contacts, practice success and reward. It compares disjoint early/late windows within the same fixed opponent, scenario and team side. Self-play opponents move with training, so their early/late results are excluded from that table. Curriculum difficulty can still change, and each cell includes sample counts.

Review notes flag sparse contacts, frequent timeouts, reward rising without scoring, large PPO updates, very low entropy and nonfinite optimizer metrics. These are prompts to investigate, not diagnoses. The exporter does not adjust rewards, learning rate or your policy automatically. Send a report whenever there is a failure; you do not need to wait for a large training budget. For performance trends, compare reports after similar budgets and repeat the held-out tests.

With your report, I can check whether the problem looks like insufficient experience, a reward shortcut, weak demonstrations, an opponent mismatch, unstable updates or a simulator/live issue, then propose and implement a targeted change. A clip helps distinguish failures that aggregate metrics cannot explain.

## Does SPS matter more than learning?

The practical target is **playing skill gained per hour**. SPS makes useful experience arrive faster; sample efficiency determines how much that experience teaches. Higher SPS can lose its value if changed batching, teacher mix or update settings reduce the amount learned. A lower PPO loss or higher shaped reward also does not establish playing strength.

NovaForge counts **one learner decision per arena step**. One decision advances **four physics ticks** at 120 ticks/second, or 30 learner decisions per simulated second per arena. Counts sum across workers. Teacher actions do not add learner samples. `fps_since_start`/`trainer/fps` averages the current session including rollout, optimization and checkpoint overhead. SB3's `time/fps` averages its current `learn()` call. Neither is raw physics-tick throughput. Other frameworks may count cars, ticks or collection-only work, so compare units before comparing numbers.

In the diverse preset, two workers × 1,024 decisions give **2,048 fresh decisions per PPO rollout**. PPO makes four epochs over this data using minibatches of 256. Increasing rollout size can raise throughput while delaying the next update; reusing the same samples for more epochs does not create new experience. SB3's `train/n_updates` counts epochs, not individual minibatch optimizer steps.

Entropy also depends on the action representation. This student has one categorical choice among 276 actions: maximum entropy is `ln(276)`, about **5.62 nats**. SB3 logs its negative as `train/entropy_loss`. Entropy numbers from bots with several action heads or different reductions are not directly comparable.

For your i5/1650 Ti laptop, start with the existing two-worker CPU preset. Measure a fixed-opponent evaluation alongside end-to-end SPS before changing workers, batches or GPU settings. Benchmarking speed with a tiny smoke run cannot predict long-run learning quality.
