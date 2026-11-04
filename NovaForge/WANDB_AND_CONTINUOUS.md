# NovaForge v1.2 — train until paused, with W&B status

The v1.1 launchers stopped after their configured decision budget. **The v1.2 mixed-training launchers run continuously until you pause or interrupt them.** The Windows checkpoint fix and all four public bot ports remain included.

## Update and start

1. If training is running, pause it with launcher 15 and wait for the save/exit. Extract the v1.2 ZIP into `Chat_GPT_AI`, replacing NovaForge source files. Keep your `.venv`, `assets`, datasets, models and runs.
2. Run **`17_WANDB_SETUP.bat`** once. It installs the optional W&B SDK into NovaForge's existing environment, then checks the saved local login.
3. Run **`18_START_OR_RESUME_WANDB.bat`**. If `diverse01` exists, it resumes that run. Otherwise it initializes from `models\mixed_bc.zip` using the diverse config. A new install needs launchers 10–12 first to download/check teachers and create that model.
4. Open the **W&B run link printed in the training console**, or run **`16_MIXED_STATUS.bat`** to see it under `wandb.url`.
5. Use **`15_MIXED_PAUSE.bat`** to request a saved stop. Wait for the trainer to report that it stopped. Run **18** again when you want to continue.

The updated **13** and **14** launchers also use continuous training with online W&B, after setup 17. Launcher 18 chooses start/resume automatically.

Your existing `diverse01` keeps its training configuration and full checkpoint. W&B can be attached when resuming a run created before this update. No repeated collection or pretraining is needed for an existing run.

## Your saved key

NovaForge calls the W&B SDK's `login(prompt=False, verify=True)`. The SDK checks its existing session, `WANDB_API_KEY`, supported W&B settings and the user's `.netrc`/`_netrc` credentials (or a `NETRC` override). That works across Python virtual environments using the same Windows user.

The cloud workspace cannot inspect your Windows drive. The launcher performs the check on your PC. A key saved only in an arbitrary text file or another program's private config cannot be discovered automatically by the standard SDK.

If setup cannot find or verify a login, run this **locally inside NovaForge**:

```bat
.venv\Scripts\python.exe -m wandb login
```

Then rerun 17. NovaForge never asks you to put a key into its configuration, source code, command-line flags or this chat. It does not scan your files for keys. If your W&B account uses a custom host or a `WANDB_MODE` setting, keep those settings consistent with online training.

The credential lookup behavior is defined by the [pinned W&B SDK's login implementation](https://github.com/wandb/wandb/blob/v0.31.0/wandb/sdk/wandb_login.py).

## What appears in W&B

| Metric group | What it shows |
| --- | --- |
| `trainer/*` | Global decisions, throughput, session episodes and continuous-mode flag |
| `train/*` | PPO policy/value loss, entropy, KL, clip fraction and learning rate |
| `rollout/*` | SB3 episode reward and length |
| `window/*` | Last 200 completed episodes: reward, touches, goal/concede/timeout fractions and practice success |
| `opponents/<bot>/*` | Goal/concede/timeout fractions and sample counts for each bot and self-play category |
| `mechanics/<scenario>/*` | Practice success and counts for shooting, defense, aerial, wall, recovery, dribble and kickoff starts |
| `rewards/*` | Mean reward components, including terminal goals and shaping |
| System metrics | SDK-supported CPU, RAM and GPU monitoring on the training PC |

Charts use **`trainer/timesteps`** as the training axis. W&B has its own event sequence, so restarting from a saved checkpoint does not cause earlier timestep events to be silently rejected. A crash can still rewind the model to the last saved checkpoint; the chart may show repeated training timesteps during recovery.

Episode statistics are rolling windows and restart with the process. First-goal scoring fractions include censored timeouts in the denominator; timeouts are not wins or draws. These are training diagnostics, not held-out full-match win rates.

W&B logging occurs in the learner process. Teacher workers do not each create a dashboard run. Model weights, replay files, source code, git snapshots and console capture are not uploaded by this integration. The selected training configuration, scalar metrics and SDK system statistics are logged.

## Resume and local status

`runs\diverse01\wandb_status.json` stores the W&B run ID, project/entity, URL and logging state. It contains no API key. Online resume uses the same ID with `resume="allow"`, continuing the same W&B run. Keep that file with the run's checkpoints.

`runs\diverse01\status.json` now includes `continuous`, the update time, and the W&B status/link. You can also inspect another run:

```bat
.venv\Scripts\python.exe run.py status --run laptop01
```

When paused, the training process saves and closes its W&B session. W&B may display that session as finished; `trainer/state` records `stopped`, and a later online resume reopens the same ID. Changing project/entity for an already tracked training run is rejected to avoid silently splitting its history.

## Continuous mode details

`--forever` repeats bounded PPO segments in the **same process, model and vector environment**. Normal segment completion does not reset the student or end the W&B run. `--steps` controls segment size in this mode rather than the overall training limit. Automatic checkpoints and frozen opponent snapshots continue between PPO updates and at segment boundaries.

The pause flag is checked after an environment step. An unfinished rollout is discarded, the current policy/optimizer is saved, and the process exits. `Ctrl+C` also requests a normal saved interruption. A reboot, shutdown, sleep, runtime error or full disk can stop progress; this update does not install a background service or restart training automatically after boot. Keep the PC powered and awake while training.

Long runs retain generated checkpoints/snapshots, so disk usage grows. The resume behavior remains approximate: environments, RNG streams and per-worker curriculum estimates restart, while policy and optimizer are restored.

## CLI controls and offline options

Resume any existing run continuously with online tracking:

```bat
.venv\Scripts\python.exe run.py train --run diverse01 --resume --forever --wandb online
```

Choose a project/team when first attaching tracking:

```bat
.venv\Scripts\python.exe run.py train --run diverse01 --resume --forever --wandb online --wandb-project novaforge --wandb-entity YOUR_TEAM
```

Use local W&B event files without login/network:

```bat
.venv\Scripts\python.exe run.py train --run diverse01 --resume --forever --wandb offline
```

Offline sessions create separate local event directories under the run's `wandb` folder. Use the SDK's printed `wandb sync` command later if you want to upload them; offline event files do not themselves provide a live website dashboard.

Disable W&B explicitly, or run a finite segment:

```bat
.venv\Scripts\python.exe run.py train --run diverse01 --resume --forever --wandb off
.venv\Scripts\python.exe run.py train --run diverse01 --resume --steps 100000 --wandb off
```

Without `--forever`, training remains bounded. Without an explicit `--wandb` mode, the saved tracking mode is reused, or tracking defaults to off for a run never attached to W&B. Launchers 18/13/14 explicitly request online mode.

An online startup requires a usable login and connection before the new training configuration is committed. A later SDK logging exception is reported as `logging_error` in local status; training/local checkpoints continue. W&B's SDK also handles its normal background buffering/reconnection. Read the actual mode/status rather than assuming a website is updating.

## Validation

The complete teacher-enabled test suite passes **38 tests**. Tests cover continuation across multiple segments, pause handling, timeout accounting, reuse of a W&B run ID, noninteractive credential lookup and visible logging failure status. A real two-worker mixed-bot run with the actual W&B SDK in offline mode crossed multiple segments, paused via STOP, saved, and resumed with the same stored tracking ID. Cloud upload/account authorization cannot be tested from this environment with your Windows credentials; verify those with launcher 17 on your PC.
