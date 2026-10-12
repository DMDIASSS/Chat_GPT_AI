# Slater v0.3.8c — Live RLBot Nexto kickoff trace, **no training**

Your v038b smoke produced 40 timeouts in 48 short episodes, so it is not adequate for selecting the strongest simulator model. Its pure 175-tick trace successfully applied 168 consecutive stock kickoff controls and then exited, but the test used a synthetic stationary ball and synthetic kickoff-pause flag.

**This patch makes a completely separate, diagnostic copy of the original RLBotPack Nexto (NOT V60).** It logs *actual* live RLBot packet flags, elapsed ticks, the neural actions that Nexto itself selected, kickoff script index, and the controller outputs every received packet. The analyzer drives the v038b `NextoV4Clock` with those **same inputs** to find the first scheduling divergence.

## Contents

- `slater_nexto_live_build_v038c.py` — create-only probe builder; checks both the archived Nexto source SHA and real original Nexto model SHA.
- `slater_nexto_probe_v038c.py` — passive, buffered JSONL recorder injected only into a new Nexto copy; max 3,600 received packets by default.
- `slater_nexto_live_analyze_v038c.py` — compares the live packet/control trace with the pure v038b scheduler, using logged actual NN actions.
- `slater_v038c_source/` — **original source files from the RLBotPack you uploaded**, with no model weights: `bot.py`, `agent.py`, `nexto_obs.py`, `bot.cfg`, `appearance.cfg`, `requirements.txt`, and logo. Only a new copy is instrumented at runtime.
- `slater_v038c_tests/` — ten offline regression tests.

## 1. Extract and run tests

Extract the ZIP into the **project root** `E:\Downloads\Chat_GPT_AI`. Do not delete or replace any Slater files. Run:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v038c_tests -q
```

Expected: `10 passed` (if the original 10 tests are present and run normally).

## 2. Build a stock Nexto diagnostic copy

The project's original Nexto weights should already exist at `vendor/nexto/nexto-model.pt`. The builder requires SHA-256:
`bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa`

Run:

```bat
.venv\Scripts\python.exe slater_nexto_live_build_v038c.py --out-bot data/isolated/slater_v038c_nexto_live01
```

Expected:

```text
V038C_DIAGNOSTIC_FOLDER E:\Downloads\Chat_GPT_AI\data\isolated\slater_v038c_nexto_live01
V038C_LIVE_CAPTURE_AFTER_PLAYING E:\Downloads\Chat_GPT_AI\data\isolated\slater_v038c_nexto_live01\capture_v038c
V038C_EXISTING_BOTS_UNCHANGED
```

The builder refuses existing output folders; **do not run it twice with the same --out-bot**.

## 3. Play in RLBot GUI

Your launcher selects a **bot folder**, not a bot.cfg path. Choose:

- Blue/Orange stock opponent: `E:\Downloads\Chat_GPT_AI\data\isolated\slater_v038c_nexto_live01`
- The other side: your protected original V60 folder `E:\Downloads\Chat_GPT_AI\data\rlbot_exports\V60`

Try one 1v1 match from each side (change sides or repeat match), normal **1× speed**, ideally stable **120 FPS, VSync off**. No need to play a full five minutes; the critical part is the kickoff. This special Nexto will print `V038C_LIVE_TRACE ...jsonl` in its console, and capture up to 3,600 received game packets.

**Logging can affect FPS slightly**; don't use probe results to benchmark win rates. Do not accidentally select your previous u60-instrumented bot as the Nexto opponent.

## 4. Analyze the live reference control trace

```bat
.venv\Scripts\python.exe slater_nexto_live_analyze_v038c.py --capture-dir data/isolated/slater_v038c_nexto_live01/capture_v038c --out data/isolated/v038c_nexto_live01.json
```

Expected `V038C_LIVE ...` and `V038C_REPORT ...`. `PASS` means the *control scheduler driven by logged real inputs* matches the reference outputs in that trace. It does **not** prove physics state transfer or RLGym observation equivalence. `REVIEW` means divergence; inspect `first_30_differences` in the JSON. Never overwrite outputs; use a new `--out` path if rerunning.

Upload **the JSON** and preferably the `nexto_live_*.jsonl` files. They contain car/ball coordinates and control vectors (not account credentials or player IDs). If you have no capture files, check the RLBot Nexto console for `SLATER_V038C_CAPTURE_ERROR` / `V038C_LIVE_TRACE`.

## Safety, reproducibility, scope

- Zero writes to u60, Cycle9, OG Champion, any other existing bot, or training checkpoints.
- The new Nexto model is copied from your known official Nexto model; SHA verified.
- Original Nexto code and lookups are unmodified except three passive capture hooks in the *new isolated copy*.
- Diagnostics focus on **source-level timing and runtime controls**, not full Rocket League ↔ RocketSim physics parity.
- Trainer remains disabled. The two-update u62 PPO attempt did not establish improvement and should remain experimental.
- If the output is mostly pre-match packets, play a new match and save the next trace; the analyzer labels the test scope.
