# NovaForge v1.0.1 — start here

If you already installed v1.0 and `1_CHECK.bat` failed with `Bad file descriptor` while saving a model, follow [HOTFIX_v1.0.1.md](HOTFIX_v1.0.1.md). You can keep your environment and downloaded assets.

A new **1v1** Rocket League research bot for Windows 10, i5-10300H, GTX 1650 Ti Mobile and 16 GB RAM. This release adds a separate training lab inside `Chat_GPT_AI\NovaForge`. Your existing Slater/GigaLearn/RLGym files and checkpoints are not inputs to this trainer and are not overwritten.

It trains a new, compact policy. No competitive pretrained student is included. The first goal is to get a reproducible training/evaluation loop working on your laptop; reaching the named bots' strength requires substantially more training and testing.

## What is included

- Real headless RocketSim physics through RLGym v2, with Stable-Baselines3 PPO.
- Frozen current-policy and historical-policy opponents, sampled once per episode.
- Optional **Ripple v1.1** and **Nexto neural policy** trainers, downloaded from pinned public commits and verified with SHA256.
- Shooting, defending, dribbling, aerial, wall, recovery and kickoff starts. A small curriculum increases difficulty as practice succeeds and gives more attention to weaker scenarios.
- Teacher imitation before PPO, with validation separated by complete episode IDs.
- Replay parsing into starting positions; teachers can generate fresh, exact simulator action labels from those positions.
- Full checkpoints with optimizer state, resume, a pause command, local logs, side-balanced screening, an RLViser stream, and an RLBot v5 export.

The bot research and unfinished work are in [BOT_RESEARCH.md](BOT_RESEARCH.md) and [PLAN.md](PLAN.md). Test evidence and limits are in [VALIDATION.md](VALIDATION.md).

## 1. Unzip and install

Extract the supplied ZIP **into your existing `Chat_GPT_AI` folder**. The result should be:

```text
Chat_GPT_AI\
    your existing files...
    NovaForge\
        0_INSTALL.bat
        START_HERE.md
        run.py
        nova\
```

Install **Python 3.11, 64-bit**, including the Windows Python Launcher. The official [Python Windows downloads](https://www.python.org/downloads/windows/) or `winget install -e --id Python.Python.3.11` can supply it. Open a new terminal after installation.

Double-click `NovaForge\0_INSTALL.bat`. It creates **NovaForge's own `.venv`**, installs a CPU PyTorch wheel and pinned training dependencies, and runs `pip check`. Package downloads need Internet access and a few GB of disk space. The ZIP does not contain a Python installation or third-party models.

CPU is the starting default. For this small policy and four-core laptop, simulator throughput can matter more than GPU optimization speed. Use the default first and record its `fps`; do not start with dozens of workers.

The Windows installer selects Python 3.11 to match RocketSim 2.2.1's internal Windows wheel tag. The advertised wheel is ABI3, but its internal metadata lists CPython 3.11; Python 3.12 can consequently produce a `pip check` platform warning even when actual physics works. Keep the selected interpreter consistent inside NovaForge's new environment.

All commands below use **Command Prompt**, opened inside `Chat_GPT_AI\NovaForge`. No environment activation is required.

## 2. Check the installation and run a short training test

Double-click `1_CHECK.bat`, then `2_SMOKE.bat`. Expected final markers are `CHECK_PASS` and `SMOKE_PASS`.

The smoke test runs actual two-worker PPO, saves a full checkpoint, resumes it, checks the exported actor against PPO, and uses a frozen actor as an opponent. Its tiny training run is a functionality check; it produces a weak student.

Manual equivalents:

```bat
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe run.py doctor
.venv\Scripts\python.exe run.py smoke --run smoke01 --workers 2
```

If reusing a manual smoke name, choose `smoke02` or another fresh name. If two workers fail on Windows, test `--workers 1` and send the error output. The Windows launchers have not been executed in this Linux build environment.

## 3. Download and check the trainers

Double-click `3_FETCH_TRAINERS.bat`, or run:

```bat
.venv\Scripts\python.exe run.py fetch-teachers --names nexto,ripple
.venv\Scripts\python.exe run.py doctor --teachers nexto,ripple
.venv\Scripts\python.exe -m pytest tests -q --teachers
```

Expect `DOCTOR_PASS` and passing tests. Files go into `assets\nexto` and `assets\ripple`, together with their licenses. These upstream materials use **CC BY-NC-SA 4.0**; preserve their attribution and terms when sharing adapted material. See [THIRD_PARTY.md](THIRD_PARTY.md).

The Nexto adapter runs its neural policy at eight physics ticks; it omits the stock scripted kickoff. Ripple runs its RL v1.1 ONNX model at four ticks with the original six-slot queue and deterministic action selection. These are documented simulator variants, and their scores should be labeled that way. Chronos and Galactus are available for later real-game evaluation through RLBot, but this release does not pretend to have headless adapters for them.

## 4. Give the new policy a teacher starting point

Double-click `4_COLLECT_RIPPLE.bat`, then `5_PRETRAIN.bat`.

Or run:

```bat
.venv\Scripts\python.exe run.py collect --teacher ripple --opponent nexto --samples 20000 --out datasets\ripple20k.npz
.venv\Scripts\python.exe run.py pretrain --dataset datasets\ripple20k.npz --out models\ripple_bc.zip --epochs 5
```

Collection puts Ripple in control of the learner's car, against Nexto, across the practice starts. Labels are **the controls actually sent to RocketSim**. With Ripple, all 276 action choices have an exact matching student action. Nexto collection is supported too; incompatible action quantizations are counted and skipped.

Pretraining writes `models\ripple_bc.zip` and `models\ripple_bc.zip.bc-report.json`. The report compares held-out action loss and accuracy before/after training. Episodes are kept wholly on one side of the train/validation split. This small demonstration set is an initialization experiment, not a ready-made champion. If accuracy stays flat, send the report and try a larger fresh collection rather than repeating the same small set indefinitely.

To rerun, use fresh dataset/model names; the commands reject existing outputs. `Ctrl+C` during collection saves the samples already collected. BC needs at least two episodes.

## 5. Run the first PPO experiment

Double-click `6_TRAIN.bat`, or:

```bat
.venv\Scripts\python.exe -u run.py train --run laptop01 --init models\ripple_bc.zip --teachers nexto,ripple --steps 100000
```

This starts a **new** run with two workers and the laptop preset. Nominal episode sampling is 20% scripted opponent, 30% latest frozen student, 20% historical students, 15% Nexto and 15% Ripple. Episode lengths vary, so these are sampling probabilities rather than equal time allocations.

The initial snapshot is the BC student. Opponents stay frozen for the whole episode. New snapshots are published between PPO updates. Run checkpoints and artifacts stay under `runs\laptop01`.

`--steps` means **additional learner decisions**, rounded up to a full PPO rollout. At four physics ticks per action, 30 decisions represent one simulated second per arena. Counts and throughput are not measures of skill.

For a clean from-scratch comparison without teacher weights or trainer downloads:

```bat
.venv\Scripts\python.exe -u run.py train --run scratch01 --steps 100000
```

Use a new run name for every configuration change. Existing old-project `.pt` models do not share this new policy's observation/action contract.

## 6. Pause, check status and resume

Use `8_PAUSE.bat` or, in a second terminal:

```bat
.venv\Scripts\python.exe run.py pause --run laptop01
.venv\Scripts\python.exe run.py status --run laptop01
```

The stop flag is checked on the next environment step. The trainer saves and exits; an unfinished rollout is discarded. Wait for the console to finish or status to say `stopped`. `Ctrl+C` also saves during normal training interruption.

Then use `7_RESUME.bat`, or:

```bat
.venv\Scripts\python.exe -u run.py train --run laptop01 --resume --steps 2000000
```

Resume uses the saved configuration and newest complete full checkpoint, repairing an interrupted latest pointer if needed. It restores policy and optimizer, but restarts environments, RNG streams and per-worker curriculum statistics; it is not an exact replay of the interrupted trajectory. A power failure can lose work since the last checkpoint. Immutable checkpoint files are completed before the atomic `latest.json` pointer is moved. A file lock blocks two trainers writing the same run.

Useful files:

| File | Purpose |
| --- | --- |
| `runs\laptop01\status.json` | State, steps and this-session throughput/outcomes |
| `runs\laptop01\latest.json` | Pointer to the last complete full checkpoint |
| `runs\laptop01\checkpoints\` | Full PPO/optimizer checkpoints with contract/hash sidecars |
| `runs\laptop01\league.json` | Current opponent pool; last 12 snapshots are eligible |
| `runs\laptop01\episodes.jsonl` | Scenario, opponent, goal/timeout and reward-component metrics |
| `runs\laptop01\logs\progress.csv` | PPO loss, entropy, KL, reward and throughput logs |
| `runs\laptop01\config.json` | Frozen experiment configuration |

Old generated snapshots/checkpoints are retained on disk for review. Watch disk use on long runs. Keep the laptop powered and awake during the run; begin with the short segment before extending it.

## 7. Evaluate improvement

Pause training first to free CPU resources, then:

```bat
.venv\Scripts\python.exe run.py evaluate --model runs\laptop01 --baseline models\ripple_bc.zip --opponents scripted,nexto,ripple --pairs 10 --seconds 30 --out reports\laptop01_eval01.json
```

This compares the trained student and its BC starting point with matched seeds, on blue and orange. `--pairs 10` means **20 first-goal trials per opponent per policy**. Timeouts are reported separately and never counted as wins or draws. These short simulator trials screen candidates; full RLBot matches are the final playing-strength test. No model becomes a champion automatically.

For mechanics screening:

```bat
.venv\Scripts\python.exe run.py evaluate --model runs\laptop01 --opponents scripted --scenarios shot,defense,dribble,aerial,recovery,wall --pairs 5 --seconds 15 --out reports\laptop01_mechanics01.json
```

The report separates first-goal outcomes from practice success: an elevated touch for aerials, a wall touch for wall starts, sustained ball-over-car proximity for dribbles, and an upright moving landing for recovery. Practice success is a proxy and does not establish mastery of a mechanic.

## 8. Watch the policy

Download the standalone [RLViser application](https://github.com/VirxEC/rlviser/releases), extract `rlviser.exe` into `NovaForge`, launch it, then run:

```bat
.venv\Scripts\python.exe run.py watch --model runs\laptop01 --opponent ripple --scenario kickoff
```

The command streams simulator states at 30 decisions per second to RLViser. Start the standalone viewer first. Training can run headless with the viewer closed.

## 9. Try the new bot in Rocket League with RLBot v5

After training:

```bat
.venv\Scripts\python.exe run.py export --model runs\laptop01
```

In the [RLBot v5 GUI](https://rlbot.org/), add `NovaForge\rlbot\novaforge.bot.toml`, select NovaForge and one opponent, and start an **offline 1v1** match. Start with Nexto or Ripple; then test against Chronos and Galactus from the botpack. The export replaces only NovaForge's own `rlbot\policy.pt` and sidecar. It needs NovaForge's `.venv` on your Windows machine.

The new export targets **RLBot v5 `.bot.toml`**. It is a new 1v1 integration; old RLBot v4 `.cfg` imports are separate. Feature parity between the simulator and compatibility-state encoder is tested. An actual Windows Rocket League match is still a required user test for timing and transfer behavior.

## 10. Add replay starting positions

Use a few local **1v1 `.replay`** files first. Put them in `my_replays`, then:

```bat
.venv\Scripts\python.exe run.py replay-import my_replays --out datasets\replay_resets.npz --stride 30 --max-states 5000
.venv\Scripts\python.exe run.py collect --teacher ripple --opponent nexto --replay-bank datasets\replay_resets.npz --samples 30000 --out datasets\ripple_replay30k.npz
.venv\Scripts\python.exe run.py pretrain --dataset datasets\ripple_replay30k.npz --out models\replay_bc.zip --epochs 5
.venv\Scripts\python.exe run.py train --run replay01 --init models\replay_bc.zip --teachers nexto,ripple --replay-bank datasets\replay_resets.npz --steps 100000
```

The parser extracts valid, non-goal, non-demo 1v1 states. Replays supply **starting positions**; fresh teacher rollouts supply the action labels. The `replay` start gets relative weight `.25` alongside the existing scenarios, and adaptation can change its sampling. This avoids treating reconstructed replay controls as exact demonstrations. Multi-player/team replays are skipped in v1.

The serialized-bank-to-simulator path is tested. A complete raw `.replay` parse was not exercised here because no replay fixture was supplied; parser-format errors should be reported with the replay parser's log. `--carball PATH` selects a custom compatible parser executable if needed.

## Optional: try the GTX 1650 Ti for optimization

Do this only after the CPU smoke works and NVIDIA drivers are installed. Inside NovaForge:

```bat
.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall "torch==2.9.1" --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe run.py doctor --teachers nexto,ripple
.venv\Scripts\python.exe run.py train --run gpu01 --init models\ripple_bc.zip --teachers nexto,ripple --device cuda --steps 100000
```

This download is much larger. The policy optimizer uses CUDA; simulator workers and frozen teacher inference remain on CPU. Compare actual throughput against `laptop01`; a tiny MLP may run faster on CPU. CUDA was not available for validation here.

## Send feedback

Send `reports\doctor.json`, the smoke report in `reports`, the evaluation JSON, the BC report, and the recent console error if anything failed. A short RLViser/RLBot clip plus the scenario/opponent is especially useful. Include whether it chases, stalls, misses kickoffs, wastes boost or fails recoveries. These observations decide the next change in [PLAN.md](PLAN.md).
