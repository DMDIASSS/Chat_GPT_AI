# Export the replay-only model to RLBot v4

The consolidated repair/training/results/export instructions are in
[REPLAY_FINAL_GUIDE.md](REPLAY_FINAL_GUIDE.md). `--scripted-kickoff` now enables an
optional basic drive/steer/boost assist, explicitly separate from model inference.

If an existing export crashes with `Arena boost layout differs from the training
observation contract` on DFH Stadium: stop the match/close RLBot, extract the
boost-fix source update into the project, then run `FIX_REPLAY_RLBOT.bat`. It
patches the existing `ReplayScratch01` folder and refreshes its integrity hashes;
weights and tokens are preserved. Restart RLBot and select the same `bot.cfg`.
The pad mapping now uses X/Y positions while retaining canonical training heights.
For another export folder, pass `--folder "full\path\to\export"` to the fix BAT.

Extract this small source update into your existing `E:\Downloads\Chat_GPT_AI`.
It adds a compatible exporter; the older 271/Nexto exporter cannot load this
temporal action-chunk architecture.

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
EXPORT_REPLAY_RLBOT.bat --run replay_scratch01 --name ReplayScratch01
```

After `EXPORTED`, import this file through RLBot **v4** Add/Load Bot:

```text
E:\Downloads\Chat_GPT_AI\data\rlbot_exports\ReplayScratch01\bot.cfg
```

Use an RLBot Python environment with Torch and NumPy installed. The export
contains `requirements.txt`. Your existing training `.venv` already has Torch
and NumPy; RLBot must use a compatible Python environment too. `runtime.json`
defaults to `auto`, selecting CUDA when available in that interpreter and CPU
otherwise. Set it to `cpu` if the RLBot interpreter has no compatible CUDA build.
The export supports standard Soccar boost layouts and up to six cars, with
automatic team-relative observations. It is an RLBot v4 Python bot, not an RLBot
v5 package or a browser/Roblox export.

The folder is self-contained and can be copied elsewhere. It contains a frozen
TorchScript `policy.pt`, the exact trained `tokens.npy`, observation code and
the RLBot entry point. It does not need the training project, RLGym or RocketSim
at runtime. Keep all exported files together. `EXPORT_INFO.json` records source
hashes, artifact hashes, architecture and numerical checks. No optimizer state
or credentials are included. Source model/vocabulary hashes are checked before
and after export. Existing export folders are never overwritten; use a new
`--name` when exporting again.

This is **direct policy inference**. It retains eight causal observation frames,
caches their spatial features, predicts an action-chunk token every eight physics
ticks, and executes its first eight controls with per-tick jump/boost/powerslide
edges. The policy is deterministic argmax. It includes neither the one-second
RocketSim candidate-search planner nor a scripted pro kickoff book. Exporting
does not retrain the network, run matches, change your training protocol or
change the trained weights.

RLBot packets do not provide every training-state flag. Jump/flip timers are
estimated from observed jumps; wheel contact is used as the ground estimate,
including wall contact. These differences can affect gameplay. Packet gaps,
clock resets, inactive rounds, demolitions and invalid model outputs clear the
controller state; errors return neutral controls and a console diagnostic.
Live Rocket League behavior and competitive strength have not been verified by
the cloud tests.

For a different trained run:

```bat
EXPORT_REPLAY_RLBOT.bat --run replay_mixed3v3_02 --name ReplayMixed3v3
```

That run must already contain a selected `best.pt` and its matching vocabulary.
It does not exist merely because a launcher was downloaded.

Validation:

```bat
.venv\Scripts\python.exe -m pytest -q tests/test_replay_rlbot_export.py
```

Tests compare packet observations against the training builder for 2/4/6 cars,
both teams and shuffled pad order; verify per-tick controls and history resets;
save/reload the actual TorchScript artifact; and load/run the exported entry
point in a separate interpreter without training-project imports. Only RLBot's
BaseAgent/controller interface is stubbed there; a live match is not launched.
An additional full-size engineering fixture checks the 3,271,683-parameter,
256-token architecture. It is not the user's private trained checkpoint.
