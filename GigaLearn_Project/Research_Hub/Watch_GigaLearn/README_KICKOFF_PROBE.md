# Kickoff AFK vs Viewer Delay — read-only diagnostic

Extract ZIP to `E:\Downloads\Chat_GPT_AI` (root of project). NO rebuild and NO installer.

Double-click `GigaLearn_Project\Research_Hub\Watch_GigaLearn\3_DIAGNOSE_NEXTO_KICKOFF.bat` and wait ~20–60 seconds. Repeat `4_DIAGNOSE_CYCLE9_KICKOFF.bat` and `5_DIAGNOSE_WAVEDASH_KICKOFF.bat`. Paste output to chat.

This runs real RocketSim physics, the existing frozen `.pt` teacher C++ bridge, and your actual `.lt` student. It prints real wall-clock gaps vs simulated time, and physical car speeds for the first 8 seconds. The `headless` viewer is intentional: eliminates drawing delays, same physics/AI code.

**Interpretation:**
- If both student and teacher move immediately in simulated time but the GUI appears frozen first: viewer warmup/buffering.
- If teacher remains <150uu/s and barely moves for 2+ simulated seconds: real kickoff policy/controls failure, not just graphics.
- If teacher moves but slowly/no boost: the native RLBot kickoff override is missing in this bridge; NN policy only.
- One kickoff is not a proper competitive evaluation; check both blue/orange episodes and all three teachers.

No modification to `.pt` or `.lt` checkpoints, `GigaLearnCPP.dll`, trainer, or existing viewer files.
