# Frozen-teacher copying — v1.5

**v1.5.2:** Existing copy02 users should run launcher **32** once, then **21**. The published student is preserved; collection now includes general scenarios and early teacher takeovers. Read [the learning update](LEARNING_UPDATE_v1.5.2.md) before interpreting old and new evaluations.


This version starts a **fresh student in `runs\copy02`** and trains it on frozen Nexto, Ripple, Chronos and Galactus simulator controls. It includes a correction for the previous-action shortcut found in v1.4. Read [COPY_CORRECTION_v1.5.md](COPY_CORRECTION_v1.5.md) for the evidence and changes.

## Update and start fresh

1. Pause the old copying process with **22** and wait for its save/exit. If status already says `stopped`, it has finished saving.
2. The ZIP contains **`chat_gpt_ai/novaforge`**. Extract into the parent of the existing project folder, for example `E:\Downloads`, and merge/replace source files. Keep `.venv`, `assets`, datasets, models and runs. Windows treats the old capitalized folder names as the same paths.
3. Run **1_CHECK.bat**. Use **3_FETCH_TRAINERS.bat** if the four teachers are missing, and **17_WANDB_SETUP.bat** if W&B needs setup. No new Python dependencies are needed.
4. Run **21_START_OR_RESUME_COPY.bat**. It starts `copy02` with new random weights, a new dataset/validation set and its own W&B run. It resumes `copy02` on subsequent launches.
5. Use **23** for status and **22** to pause/save. Run **21** to resume. Collection and fitting continue until paused.

The earlier `copy01` stays available for viewing, exporting and comparison. Its old transition-filtered data is not used for the fresh run. Resuming that legacy training objective through the corrected trainer is rejected with an explanation. Launchers 22–27 prefer `copy02` once it exists, and otherwise address `copy01` so you can still inspect the old bot.

## What changed in the labels and actor

Chronos/Galactus can change their controls on the last physics tick of a four-tick student window. The old collector discarded those windows and retained mostly examples where the target equaled the previous action. That gave a student an easy shortcut: repeat the last controls, including idle controls at startup.

The corrected mode retains these transitions. A mixed window uses its **last actually executed control** as the student's constant-action target. Stable windows are exact; changed windows approximate the teacher's timing by up to a few physics ticks. Incompatible button/analog mappings are still excluded. Initial all-zero controls are skipped until the first nonzero teacher control, removing delay-queue warmup examples; this also omits deliberate initial coasting.

The actor's previous-action input columns are fixed at zero during initialization, fitting and resume. Export preserves those zero weights, so deployment cannot reintroduce the shortcut. Validation reports both ordinary copying agreement and the repeat-previous-action baseline, plus results for changed versus held controls. Changed-control examples receive extra supervised weight, normalized within each teacher.

## First learn to reach the ball

The fresh student begins with **teacher kickoff approaches ending at the teacher's first ball touch**. This concentrates demonstrations on driving, steering and acceleration rather than letting long post-kickoff sequences dominate the action frequencies.

After each fitting round, the student's own policy plays a small fixed monitoring set against the scripted opponent. Once the selected student contacts the ball in at least 75% of that set, collection expands to the configured shooting, defending, dribbling, aerial, wall, recovery and kickoff distribution. Some first-touch kickoff segments remain in the mix. In the general stage, frozen teachers also take over from student-reached states to provide correction demonstrations.

These monitoring trials are feedback used during development/selection. They are not an independent final test or a full-match win rate.

## Round defaults

| Stage | Behavior |
| --- | --- |
| Teacher bank | All four pinned public adapters, with verified immutable weights and no teacher gradients |
| Validation | 10,000 teacher decision attempts on separate rollouts, rotating through all positive-weight scenarios; retained across resume |
| Fresh training | 50,000 teacher decision attempts per round |
| Active buffer | At most 250,000 accepted labels, retaining recent complete shards |
| Fitting | Ten supervised epochs per round, with teacher balancing, transition attention and mild shared-return weighting |
| Deployment selection | Student kickoff contacts first, then scoring/conceding and copying loss break monitoring ties |
| Resume | Latest optimizer state, including a partially completed fitting round |

One teacher decision spans four simulator ticks. Student-prefix decisions and monitoring games are not counted as new teacher labels. Local generations accumulate on disk even when older shards leave the active RAM buffer.

The smallest validation loss and the model selected for gameplay can differ. `best_validation` describes the best copying-loss checkpoint. `selected_validation`, `last_student_probe` and the published checkpoint describe the model used for viewing/export. Before the first round finishes, that published checkpoint is the initial student; let collection and fitting complete before judging it.

## Approximate reward transfer

The teacher networks do not expose their original reward code. Collection records the shared NovaForge simulator reward—goals, touches, approach, ball progress, altitude and boost cost—and computes discounted returns over executed teacher steps. Supervised losses mildly favor better-return examples within each teacher. Return factors stay between 0.5 and 1.5 and average one; unfinished end-of-chunk returns stay neutral. Lower-return examples are retained.

This transfers a preference for demonstrated outcomes under a common score. It does not recover the creators' hidden training reward functions. **PPO is not used** in this copying mode, and teacher-rollout rewards are not presented as the student's playing score.

## Watch, export, evaluate and report

- **24_WATCH_COPY.bat:** automatically finds/opens RLViser with learner ballcam. The search starts at `chat_gpt_ai\rlviser.exe`. The checked camera build provides horizontal FOV 110, distance 270, height 100 and pitch offset −4, with no added shake. See [RLVISER_CAMERA.md](RLVISER_CAMERA.md).
- **25_EXPORT_COPY.bat:** export the selected student as `.lt` + `.bot.toml` + Python runtime under `exports`. Add the printed TOML in RLBot v5 and play offline 1v1. See [V5_EXPORT.md](V5_EXPORT.md).
- **26_COPY_REPORT.bat:** export a small metrics/coverage/gameplay-monitoring ZIP to upload in the chat.
- **27_EVALUATE_COPY.bat:** while paused, run the student against the scripted bot and all four named bots. If `copy01` exists, the corrected `copy02` is compared against that earlier student; otherwise it uses its initialization.
- **30_EVALUATE_COPY_MECHANICS.bat:** while paused, test all seven scenarios against the scripted opponent, including dribble coverage. It then exports a report.

Launcher 27 runs 50 first-goal trials per policy, 100 total. Launcher 30 runs 70 per policy, 140 total. Timeouts remain separate. Both are preliminary simulator screens; actual offline RLBot matches on alternating colors are the transfer check. Use **29** to export the older `diverse01` PPO bot. Launcher **18** continues that older PPO workflow.

## Dashboard and CLI

W&B reuses the SDK's local login. `copy/train_loss`, `copy/validation_*`, per-teacher/per-scenario/per-transition metrics and `copy/student_*` show different parts of progress. Dashboard links on the current CoreWeave Forge domain are retained by the report exporter.

`trainer/timesteps` counts collected training teacher decisions, including discarded label attempts. `copy/gradient_updates` counts supervised minibatches, and `copy/examples_seen` counts reused examples across epochs. These are not a learner win rate.

From Command Prompt inside `novaforge`:

```bat
.venv\Scripts\python.exe run.py copy-train --run copy02 --forever --wandb off
.venv\Scripts\python.exe run.py copy-train --run copy02 --resume --forever --wandb off
.venv\Scripts\python.exe run.py copy-report --run copy02
.venv\Scripts\python.exe run.py watch --model runs\copy02 --config runs\copy02\config.json --opponent nexto --scenario kickoff
```

A single-teacher experiment uses a separate fresh name, for example `--run chronos_copy --teachers chronos`. Stored teacher/configuration settings are reused on resume. Choose a fresh name to change the experiment. Teacher licenses and simulator-port limits remain in [THIRD_PARTY.md](THIRD_PARTY.md) and [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md).
