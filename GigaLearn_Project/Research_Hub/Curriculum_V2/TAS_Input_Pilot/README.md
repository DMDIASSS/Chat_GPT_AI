# TAS input-memory pilot — experimental, isolated

**This is NOT native GigaLearn TAS behavior cloning and will NOT fix circles/backflips in game.**
The current TAS `.data` recordings do not provide verified aligned car/ball physics states per frame. Without that, it is not possible to compute a meaningful position-tracking loss for a neural gameplay policy.

This add-on implements the one small piece that is possible without guessing:

1. Audit the 32-byte TAS input frames and report tentative starting car and ball coordinates from the 128-byte trailer.
2. Train a **separate, time- and file-conditioned neural input-memory model** to reproduce seven raw controller channels and seven flag bits for recorded TAS clips. This is a motor *sequence* memorization sanity check, **not** a RocketSim state-feedback policy. It uses the last 15% of each clip as a temporal holdout, which is not heldout-clip gameplay validation.
3. Write an alternating Nexto → Cycle 9 → Wavedash **schedule only** for the future native opponent bridge. The script never pretends to run matches.

Inputs are read-only. Models live under `TAS_Input_Pilot/results/tas_input_<timestamp>/` and are named `tas_input_memory.pt` so they cannot be mistaken for native GigaLearn `.lt` policy weights. They **must not** be seeded into Research Hub PPO.

## How to run on Windows

Extract the ZIP into `E:\Downloads\Chat_GPT_AI`. Your TAS folder is expected at `E:\Downloads\Chat_GPT_AI\data\tas`. If it is elsewhere, **drag the folder onto the BAT** to pass its path.

- Run `1_INSPECT_TAS.bat` to list usable TAS clips and show candidate initial car/ball XYZ coordinates.
- Run `2_TRAIN_TAS_INPUT_MEMORY.bat` for a five-epoch input-sequence fitting test. CPU PyTorch from your project `.venv` is used. Do not expect playable Rocket League AI from this output.
- Run `3_PLAN_ALTERNATING_OPPONENTS.bat` to generate `alternating_opponents_plan.json`.

## Essential missing bridge for useful TAS learning

- Verify exact TAS plugin binary layout and flags, initial **rotation and velocity** as well as position, tick rate, and the original map/hitbox.
- Replay the inputs in RocketSim, capture the **state every frame**, visually validate against original TAS footage or synchronized in-game telemetry.
- Only then distill `(AdvancedObs(state), discretized action)` pairs into a **new isolated GigaLearn `.lt` checkpoint**, with playback drift and a learned-vs-scripted trajectory metric.
- Build native `.pt` Nexto/Cycle 9/Wavedash frozen opponents with correct observation/action adapter; alternate opponents across short match blocks, side-swapped. Do not say this is done until verified.

Research Hub original models, replays and TAS recordings are not modified. This does not replace the Curriculum app or its data; it adds a safe pilot alongside them.
