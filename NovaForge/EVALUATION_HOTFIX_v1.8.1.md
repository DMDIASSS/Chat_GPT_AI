# Selector evaluation blank/slow console fix

The manual selector evaluator was missing the one-thread Torch setting used by training and the main league evaluator. It inherited Torch's CPU defaults; that can make repeated small-network inference much slower on a laptop. It also printed nothing while loading both sets of experts, then waited for eight games before the first match summary.

This update sets one Torch thread before model loading, starts launcher 7 with unbuffered output and local OMP/MKL limits, and prints:

- Startup: game count, simulated duration, selected checkpoint step/hash and Torch threads.
- Separate latest/baseline model loading phases.
- Every game start and final score, with opponent and team side.
- A running score/simulation-time heartbeat about every five wall-clock seconds during play.
- The exact completed result path, triadbot/runs/selector01/wdl.json.

The default remains **32 games total**: 16 latest-selector games and 16 initialization games, each 60 simulated seconds. Runtime depends on the PC; visible progress does not imply each game finishes instantly. No training weights, selection policy or match rules are changed by this fix.

## Update

1. Press Ctrl+C and close the old evaluation console. Pause selector training with 8 if it is still running, and wait for its console to finish saving.
2. Download the combined evaluation-fix ZIP. Inside its chat_gpt_ai folder, copy novaforge and triadbot into your existing Chat_GPT_AI folder, replacing program files. Keep .venv, assets and runs.
3. Run 7_EVALUATE_SELECTOR.bat again. You should immediately see a launcher message, followed by loading messages and GAME 1/32.
4. After SELECTOR_WDL_READY, send the printed wdl.json path's file and selector01/status.json.

A still-running trainer now produces a clear pause instruction. Ctrl+C cancels evaluation without editing weights or replacing an earlier complete result; the console explicitly identifies cancellation so an old wdl.json is not mistaken for new results.

For a short **pipeline check**, from triadbot:

```bat
..\novaforge\.venv\Scripts\python.exe -u run.py selector-evaluate --pairs 1 --seconds 1
```

This uses 16 one-second games and is too short to assess strength. Use normal launcher 7 for the actual comparison.
