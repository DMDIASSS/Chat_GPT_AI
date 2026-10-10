# Watch the actual frozen `.pt` teachers inside RocketSim

This is NOT the old Watch GigaLearn screen showing `.lt` students.
This adds a **separate read-only viewer** (`GigaLearnWatchTeacher.exe`) that runs real Nexto / Cycle 9 / Wavedash teacher inference via the SAME `FrozenNextoBridge` and isolated Python worker as the training pipeline. The other car is an existing `.lt` student. Both cars alternate sides across episodes. No checkpoints are written or model weights changed.

## Installation

Extract ZIP over the **Chat_GPT_AI root**, not inside Watch_GigaLearn.

1. Run `GigaLearn_Project\Research_Hub\Watch_GigaLearn\0_INSTALL_ACTUAL_TEACHER_WATCH.bat`.
2. Open **x64 Native Tools Command Prompt for VS 2022**, then run:
   `E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Watch_GigaLearn\1_BUILD_ACTUAL_TEACHER_WATCH.bat`
3. Run `2_WATCH_ACTUAL_TEACHERS.bat`.
4. Choose Blue/model A `tri_teacher_challenger_01`; choose B `frozen:nexto`, then `frozen:cycle9`, then `frozen:wavedash`. Watch at speed 1.0x. Wait for at least one episode summary.

## What confirms/disproves the problem

The output prints `TEACHER_EPISODE` with `steer_ticks`, `boost_ticks`, `jump_ticks`, `teacher_touches`. These are **actual applied teacher actions** and physics-based ball-touch counts, not action shapes or PPO loss. The GUI displays true teacher movement in RocketSim.

- Steering counts above zero only prove steering inputs are being applied; a model that drives in circles may still have a problem.
- If teacher touches are consistently zero or gameplay is obviously broken, **do not extend training**. Preserve the 1M challenger, inspect the observation mapping and kickoff controls first.
- Nexto RLBot includes a hard-coded kickoff routine that this live teacher bridge does not reproduce. This discrepancy should be fixed and evaluated separately if teachers fail kickoffs; the bridge's neural inference is otherwise unchanged by this diagnostic package.
- Teacher inputs are always **greedy** (same as PPO bridge); the `sample` dropdown only affects the student's .lt policy.

On a crash, share the log or screenshot; don't delete checkpoints or rebuild the original learner.

**Known limitation:** This C++ program must be compiled on your Windows environment. Package source was checked and Python parts tested locally, but the Windows C++ target cannot be executed in this sandbox. Do not assume the tool is working until it displays real teacher gameplay and a summary.
