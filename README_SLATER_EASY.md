# Slater Easy — safe companion for your existing `Chat_GPT_AI`

This patch adds a **minimal Windows control app**, local/W&B monitoring, and a read-only diagnostic of the failed `.pt` -> `.lt` attempt. It does **not** overwrite `update180`, modify any trainer or reward source, change an existing campaign protocol, or replace the stock GigaLearn checkpoint. It delegates training, evaluation, historical opponent selection, improvement gates, and next-routine transitions to your **existing** `slater_native_attention.py` + `slater_champion_campaign.py`.

> **Status:** The Python components have local unit/syntax tests. Native Windows CUDA, real `update180` inference, simulator wins, and a live W&B session require testing on your PC. None are claimed here.

## Install

1. Make a **backup** of `E:\Downloads\Chat_GPT_AI`, including its ignored `data/` directory.
2. Unzip this patch **into that `Chat_GPT_AI` root** (the directory containing `slater_champion_campaign.py`). It only adds new files. If a file already exists under the same name, inspect differences first.
3. Do not interrupt an unrelated running training process. This companion uses a separate campaign name and existing backend; GPU/CPU contention may slow another trainer. Wait for its safe checkpoint/pause before launching the new campaign.

## First run on your Windows PC

Before any substantial training, validate the same native attention architecture and model weights:

```bat
cd /d E:\Downloads\Chat_GPT_AI
ATTENTION_NATIVE.bat build
ATTENTION_NATIVE.bat parity --run easy_parity01 --source "data\isolated\mechanics_curriculum\selected7_mechanics01\update_000180.pt"
ATTENTION_NATIVE.bat smoke
```

A successful source SHA/parameter comparison is necessary but **not sufficient**: the parity command should also compare observations, logits/actions, action timing, and PPO. Check the produced report. Do not trust a source checkpoint that is missing or silently replaced by unmodified Nexto.

Next double-click **`SLATER_EASY.bat`** or **`SLATER_EASY_GUI.vbs`**. The interface deliberately contains only **Check, Start new, Resume, Pause safely, Open reports, and Open W&B dashboard**. For a fresh campaign, leave `slater_easy01` and 1v1 focus selected. `Start new` never resumes an existing name and never overwrites the model.

The campaign chooses existing battle routines, evaluates against frozen opponents on paired seeds, retains weaker/inconclusive candidates, and advances to the next routine automatically **within the existing controller's finite 8-cycle / 240-minute defaults**. It uses only your local hardware; Codex/ChatGPT does not need to remain open. You may change the config for a NEW run, not one already pinned to a protocol.

### Commands

```bat
SLATER_EASY.bat check
SLATER_EASY.bat status --run slater_easy01
SLATER_EASY.bat start --run slater_easy01 --mode 1v1
SLATER_EASY.bat pause --run slater_easy01
SLATER_EASY.bat resume --run slater_easy01
SLATER_EASY.bat audit --target "E:\Downloads\My_AI\GigaLearnCPP-Leak-main\build\Release\checkpoints\11318784"
```

**Important:** The `start` command is a *new* experiment and must be used only when no other GPU-intensive experiment is competing. To continue after a checkpoint-safe pause, use `resume`. The backend's process lock rejects duplicate owners for the same campaign; this UI also rejects reusing a campaign folder for `start`.

### W&B live dashboard

Log in once using the project's venv on your PC:

```bat
.venv\Scripts\python.exe -m pip install wandb
.venv\Scripts\python.exe -m wandb login
```

Enter your **new private API key locally**. Never put the key in any `.bat`, config, chat, or GitHub commit. The previous public key should be rotated. With local credentials, launching a campaign starts an independent W&B monitor, writing to the `slater-ai` project with a stable run ID and your campaign as the group. The viewer shows `W&B dashboard` once connected. If W&B is unavailable, local JSONL events continue.

The telemetry process **mirrors actually persisted per-update native PPO losses, policy KL, entropy, throughput, campaign status, evaluation-game count, routine, and confirmed promotions**. It does not fake PPO loss, invent win rates, or upload checkpoints. Independent reports and the actual campaign controller—not W&B—determine promotions. The monitor is an optional companion: if it crashes, the trainer does not stop. Existing campaigns can be monitored manually:

```bat
.venv\Scripts\python.exe slater_easy_monitor.py follow --run slater_easy01 --mode auto
.venv\Scripts\python.exe slater_easy_monitor.py status --run slater_easy01
.venv\Scripts\python.exe slater_easy_monitor.py once --run slater_easy01
```

Logs/reports:

- `data/isolated/easy_console/<run>/training.log` — Windows launcher log
- `data/isolated/easy_console/<run>/monitor.log` — W&B bridge log
- `data/isolated/easy_monitor/<run>/events.jsonl` — durable local telemetry
- `data/isolated/easy_monitor/<run>/bridge_state.json` — monitor state and dashboard link
- `data/isolated/champion_campaigns/<run>/progress.json` — campaign state
- `data/isolated/champion_campaigns/<run>/selected.json` — selected *experiment* champion
- `data/isolated/champion_campaigns/<run>/branches/` — promotion evidence

### Why the old GigaLearn `.lt` bot may have been weak

The stock GigaLearn layout (`POLICY.lt`, `SHARED_HEAD.lt`, `CRITIC.lt`, optimizer `.lt`s, and `RUNNING_STATS.json`) is **not** the layout of your 44-tensor, 444,032-parameter Nexto attention policy. A PyTorch `.pt` file can contain many different network architectures, and TorchScript `.lt` files are only containers. Converting the *file extension* or recreating a similarly sized network does not preserve weights or gameplay.

Use the read-only `slater_transfer_diagnose.py` to inventory/hashes/identify archives. It deliberately reports `transfer_verified: false` until actual **source-to-native inference parity** is established. The newer `slater_native_attention.py` already checks parameter equality during private export; test its `parity` command before additional training.

## Guardrails

- Nothing automatically replaces your RLBot playing model.
- No private model is included in this patch. Missing `update180` aborts training.
- Backend/CUDA/compiler missing? Finish setup and parity first; the GUI isn't a substitute for build tools.
- This is not a claim of beating Nexto, SSL, or improving the champion. Use independent multi-goal games, both colors and held-out starts to establish strength.
- Launching this companion **does not** attach to or stop an unrelated already-running GigaLearn run. Never replace binaries loaded by an active process.

## Local verification checklist (NOT YET RUN ON YOUR PC)

1. `SLATER_EASY.bat check` shows all required files, including the compiled `SlaterAttentionNative.exe`.
2. `SLATER_EASY.bat audit --target "PATH_TO_OLD_LT_CHECKPOINT_FOLDER"` classifies the stock `.lt` layout but **does not** falsely report transferred knowledge.
3. Verify source SHA + 44-tensor/444032-param identity with `slater_transfer_diagnose.py --inspect-model`.
4. Run the parity + smoke commands near the top of this guide; check strict source-to-native logits/actions and learned-kickoff semantics.
5. With other resource-heavy jobs safely paused, start a **fresh named** campaign. Confirm `progress.json` and isolated native `checkpoints` appear.
6. Confirm one saved `update_*.json` causes a local `events.jsonl` entry containing real `native/rollout_policy_kl` and throughput; W&B URL appears if logged in.
7. Request Pause; wait for `PAUSED`, and Resume. Verify no original update180 bytes changed and evaluation uses fresh seeds.
8. Treat simulator promotions as *experimental*, not certified strength; verify longer offline RLBot matches before using as your playing bot.
