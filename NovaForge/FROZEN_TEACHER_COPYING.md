# Copy frozen teachers

v1.4 adds **supervised teacher copying**, separate from PPO/self-play. Frozen Nexto, Ripple, Chronos and Galactus simulator adapters drive the car. Their executed controls become the student's targets. The student copies those controls with mild weighting by shared simulator returns. PPO updates are not used. The original teachers’ training reward functions cannot be recovered from their weight files.

## Start on your existing Windows install

1. Pause the old PPO run with **15_MIXED_PAUSE.bat** and wait for its save/exit.
2. The ZIP contains `chat_gpt_ai/novaforge`. Extract into the **parent** of your existing project folder and merge its source files; on your current setup that is `E:\Downloads`. Windows treats `Chat_GPT_AI\NovaForge` and the lower-case names as the same paths. Keep `.venv`, `assets`, datasets, models and runs.
3. Run **1_CHECK.bat**. Reporting/copying adds no new core dependencies.
4. If you have not downloaded all four teachers, run **3_FETCH_TRAINERS.bat**. Run **17_WANDB_SETUP.bat** if W&B has not been set up; it reuses the SDK's saved local login.
5. Run **21_START_OR_RESUME_COPY.bat**. It creates a fresh student in **runs\copy01**, or resumes that copy run. It continues until paused. Your earlier `diverse01` remains available for comparison.
6. Let at least the first demonstration round and its ten fitting epochs finish. Use **23_COPY_STATUS.bat** for phase, supervised update counts and best validation metrics. The console prints `COPY_EPOCH` after each completed fitting epoch.
7. Pause with **22_PAUSE_COPY.bat** and wait for `COPY_STOPPED` before testing. Resume later with **21**.

The initial collection phase can take time: it gathers a fixed validation set and then the first training set. The first saved checkpoint is an untrained starting model; useful inspection begins after fitting epochs have completed. Defaults use one CPU collection process and one Torch thread, suitable as a starting point for the i5/16 GB laptop. Elapsed time needs measurement on that machine.

## What happens each round

| Stage | Default behavior |
| --- | --- |
| Frozen teacher bank | All four pinned public adapters; SHA256-verified assets; neural parameters remain in evaluation mode without gradients |
| Validation | 10,000 teacher decision attempts on separate episode rollouts, collected once and retained across resumes |
| Fresh training data | 50,000 teacher decision attempts per round; teachers rotate by episode; kickoff starts have 50% sampling weight |
| Active training buffer | At most 250,000 accepted labels, retaining recent complete shards |
| Fitting | Ten supervised epochs per round; cross-entropy over the student's 276 discrete control choices; each teacher receives equal aggregate loss weight |
| Reward-weighted copying | Prefer labels with better discounted shared simulator returns. Factors stay between 0.5 and 1.5 and average one within each teacher; unfinished returns stay neutral |
| Action-history robustness | Previous-action features are zeroed on 15% of fitting rows to reduce a shortcut that repeats the preceding action forever |
| Takeover corrections | After the first round, 25% of collection episodes begin with up to two simulated seconds of the best student. A frozen teacher then takes over and supplies the labels. Student-prefix actions are never used as demonstration targets |
| Saved model selection | The lowest mean per-teacher validation loss chooses the model used for viewing/export. A separate latest optimizer checkpoint supports resume |

Each decision spans four simulator ticks. Teacher schedules/delays are preserved. Windows containing a control change within those four ticks are excluded, as are incompatible button/analog mappings. Consequently, accepted label counts can be lower than attempted decision counts. These are hard action targets, rather than every teacher's full action-probability distribution.

Takeover collection uses a fresh teacher reset at the takeover state, then records controls the teacher actually executes. It does not query a shadow teacher with fictitious action history. Validation remains pure teacher play with separate seeds. Separate episodes do not imply that every kickoff state is unique: Rocket League has a small set of standard kickoff starts.

## Watch, export, evaluate and send a report

- **24_WATCH_COPY.bat:** view the best student against the scripted opponent in RLViser. Open the standalone [RLViser Windows application](https://github.com/VirxEC/rlviser/releases) first.
- **25_EXPORT_COPY.bat:** export the best student as **policy.lt + bot.bot.toml + Python runtime** under `exports`. In the [RLBot v5 GUI](https://rlbot.org/), add the printed `.bot.toml` path and run an offline 1v1. See [V5_EXPORT.md](V5_EXPORT.md).
- **26_COPY_REPORT.bat:** create a small ZIP under `reports`. Open `progress.html` inside it or upload the ZIP in the chat. It contains validation/control metrics and matching evaluations, without weights, raw trajectories or credentials.
- **27_EVALUATE_COPY.bat:** while paused, compare the best student against its initial checkpoint using the scripted bot and all four named bots, five seeds and both sides, 20 seconds per trial. It then exports the copy report.

The comparison is 50 trials per checkpoint, 100 total. These are short first-goal simulator trials. Timeouts are separate. For watching against another bot:

```bat
.venv\Scripts\python.exe run.py watch --model runs\copy01 --config runs\copy01\config.json --opponent nexto --scenario kickoff --seconds 20
```

Use **21** for the copying run. Launcher **18** continues the older PPO workflow. The copying model is not automatically passed into PPO.

## Approximate reward transfer

The teacher networks do not expose their original reward code. Collection records the shared NovaForge simulator reward (goals, touches, approach, ball progress, altitude and boost cost), then computes discounted returns over every executed teacher step, including windows excluded from action labels. Supervised losses gently favor better-return examples within each teacher. Censored end-of-chunk returns remain neutral, and lower-return examples retain at least half weight. Per-teacher mean weighting stays one.

This transfers a preference for demonstrated outcomes under a common score; it does not recover the creators’ hidden reward functions. Validation still measures unweighted action agreement on separate episodes. `copy/teacher_reward_mean` and `copy/complete_return_fraction` expose data quality; those values describe teacher rollouts, not the student’s match score.

## Dashboard and metrics

Launcher 21 requests online W&B. Credentials are handled by the existing SDK login, as described in [WANDB_AND_CONTINUOUS.md](WANDB_AND_CONTINUOUS.md). Status 23 includes the dashboard URL/state.

`copy/train_loss` and `copy/validation_*` show supervised progress. `copy/by_teacher/*` and `copy/by_scenario/*` separate teacher/scenario performance. The report includes exact action agreement, control mean absolute error, button agreement, validation sample counts and validation loss. Balanced validation loss gives equal weight to each represented teacher. Control MAE is measured against accepted quantized teacher targets. Button agreement alone can look high because many frames contain no jump or boost.

The dashboard's `trainer/timesteps` axis counts collected training teacher decisions, including discarded label windows; validation collection and student-prefix decisions are separate. `copy/gradient_updates` counts supervised minibatch updates and `copy/examples_seen` counts training examples reused across epochs. These counts are not PPO environment steps or a learner win rate. Teacher-rollout outcomes are not reported as student performance.

## CLI alternatives

Start/resume without W&B, or run a bounded experiment:

```bat
.venv\Scripts\python.exe run.py copy-train --run copy01 --forever --wandb off
.venv\Scripts\python.exe run.py copy-train --run copy01 --resume --forever --wandb off
.venv\Scripts\python.exe run.py copy-train --run copy_small --samples 20000 --validation-samples 5000 --epochs 10 --rounds 3 --wandb off
```

Clone one teacher in a separate experiment, or initialize from an existing policy:

```bat
.venv\Scripts\python.exe run.py copy-train --run chronos_copy --teachers chronos --forever --wandb online
.venv\Scripts\python.exe run.py copy-train --run copy_from_diverse --init runs\diverse01 --forever --wandb online
```

The default is a fresh student. `--init` copies an existing policy's weights into a new supervised run with a fresh optimizer. A resumed copy run uses its stored teacher/configuration/data settings; `--rounds`, `--forever` and W&B mode control the new session. To change teachers or fitting settings, choose a new run name. A changed teacher lock is rejected on resume.

Pause is checked during collection and between minibatches. Partial collection shards and in-progress optimizer weights are saved. An interrupted fitting epoch may be repeated after resume. Checkpoint/data files are immutable generations; a crash can leave an unreferenced file but does not publish it as the best model. Local files accumulate during long runs even when older shards leave the active RAM buffer.

## What this can and cannot establish

Action agreement and lower validation loss establish that the student is learning the demonstrations. They do not guarantee better match play. A small student's observations differ from the large teachers' observations, and the public simulator adapters retain their documented timing/prediction/contact limitations. Multiple teachers can prefer different valid moves in similar positions. A single-teacher experiment is available when that disagreement becomes a bottleneck.

Use live clips and the fixed-opponent comparison to judge playing behavior. Keep attribution and the downloaded teachers' terms with shared work; see [THIRD_PARTY.md](THIRD_PARTY.md) and [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md).
