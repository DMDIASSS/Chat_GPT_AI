# Chat GPT AI — Watch latest self-play

**This add-on runs inference only: no training, no saved weight modifications.**

## Setup

Copy all files from this ZIP directly into `E:\Downloads\Chat_GPT_AI` **beside** `train.py`, `native_nexto.py` and `nexto_teacher.py` (if installed). Do NOT delete or move your `data` directory or old `watch.py`.

### One-click Windows launchers

- **`WATCH_LATEST_AI.bat`** — Recommended. Lists saved models, picks the most recently modified *trained* policy from the PPO, distilled student, and fine-tuned native Nexto families. Shows its full path before playback. The original unmodified Nexto model is excluded from auto-selection.
- **`WATCH_LATEST_GROUNDED.bat`** — Latest model in grounded-ball starts rather than kickoffs. Requires Grounded Upgrade files.
- **`WATCH_LATEST_PPO.bat`** — Highest-numbered checkpoint within `data/checkpoints/chat_gpt_ai/`, not the old `smoke_backup` folder.
- **`WATCH_STUDENT_V2.bat`** — Most recently modified `data/nexto_student*.pt` checkpoint, including future V3/V4 versions. This is the 92-input distilled student, not the original Nexto architecture.
- **`WATCH_NATIVE_LATEST.bat`** — `data/native_nexto/last.pt`, which holds fine-tuned **original Nexto attention weights**. If you haven't run native fine-tuning yet, this model does **not** exist; launch `WATCH_ORIGINAL_NEXTO.bat` instead.
- **`WATCH_ORIGINAL_NEXTO.bat`** — Watch the untouched original Nexto model vs itself.
- **`LIST_MODELS.bat`** — Display candidates without opening RLViser.

Note: the special auto mode finds the **latest written model file**, which is not necessarily the **best** model. For PPO it finds the **highest step-numbered** checkpoint even if an older checkpoint is copied recently. If the exact file matters, choose `--model` or `--checkpoint` explicitly.

### Manual commands

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe watch_latest_ai.py --list
.\.venv\Scripts\python.exe watch_latest_ai.py --model auto
.\.venv\Scripts\python.exe watch_latest_ai.py --model ppo
.\.venv\Scripts\python.exe watch_latest_ai.py --model student
.\.venv\Scripts\python.exe watch_latest_ai.py --model native
.\.venv\Scripts\python.exe watch_latest_ai.py --model nexto
.\.venv\Scripts\python.exe watch_latest_ai.py --model auto --start grounded --speed 0.75
.\.venv\Scripts\python.exe watch_latest_ai.py --model student --checkpoint data\nexto_student_v2.pt
```

`--actions sample` is the default. `--actions greedy` always chooses the most probable action, which can make weak policies repeatedly spin or collide. `--start kickoff` tests 1v1 match opening; `--start grounded` uses your Grounded Upgrade curriculum and requires it to be installed. `--episodes 0` (default) loops indefinitely; `Ctrl+C` stops. `--decisions 900` ends a round after about 60 simulated seconds if nobody scores.

### Observability

The terminal prints the full checkpoint **before** loading any model, then once every ~10 simulated seconds prints touches and goals. Blue and orange both use the **same neural-network weights**, but are given their own observations and previous-action history. Each play session resets at a goal or decision limit.

### If RLViser doesn't appear

The main launcher installs `rlgym[rl-rlviser]` if missing, and downloads RLViser v0.8.7 if missing; it **never replaces** an existing executable. The old compatible `rlviser-py` protocol uses v0.8.x. v0.9.x viewer binaries have an incompatible protocol. If you downloaded a new 0.9.x viewer separately, restore the old working viewer. If you want to use the other launchers, run `WATCH_LATEST_AI.bat` once to install viewer dependencies first.

### About strength and mechanics

**Watching isn't training.** The native Nexto model starts with Nexto's existing learned ability, while your `nexto_student_v2.pt` is the much weaker 92-feature distilled student. Neither a new viewer nor a few epochs of imitation automatically add flip resets, air dribbles, pinches, ceiling shots, or double taps.

To get a stronger bot: benchmark native baseline vs native fine-tuned on several seeds, keep best-performing checkpoints, implement **mechanic-specific RocketSim resets** and objective metrics (kickoff first-touch speed, aerial ball control, flip reset contact, useful shots), and train on those without catastrophic forgetting. Only claim improvements when offline match win rate and mechanic-success rates rise. Consider adding a learned specialist kick-off policy or validated scripted fallback as a separate module, rather than destroying general play with kickoff-heavy PPO.

Nexto-derived code/model is licensed CC BY-NC-SA 4.0 by the upstream project. Preserve attribution; do not use in commercial contexts without appropriate permissions. Use in offline Rocket League / RocketSim only.
