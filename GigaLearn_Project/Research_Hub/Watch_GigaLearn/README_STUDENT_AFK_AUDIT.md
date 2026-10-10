# Read-only student AFK regression audit

Your real frozen Nexto moved within 0.20 simulated seconds, while the 1-million-step challenger never moved over two 8-second kickoff tests. This tool checks **whether the student is naturally motionless or whether PPO training made it worse**.

## Install

Extract the ZIP to the Chat_GPT_AI root, merging `GigaLearn_Project/Research_Hub/Watch_GigaLearn`. **Do not extract into the Watch_GigaLearn folder itself.** Keep your existing `GigaLearnWatchTeacher.exe` binary, trained checkpoints and frozen opponent worker as-is. No C++ rebuild.

Double-click `GigaLearn_Project\Research_Hub\Watch_GigaLearn\6_AUDIT_STUDENT_AFK.bat`.

The program tests the earliest, middle and latest available challenger `.lt` checkpoints, with **greedy** and **sampled** actions (two kickoffs on alternating sides each). It uses `frozen:nexto` as a live control. Reports go into `Watch_GigaLearn/reports/student_afk_audit_*.json`. It never writes to checkpoint folders or training configuration. It may take a minute or two on your Windows machine.

## Interpret

- **Greedy idle, sampled moves:** the actor assigns its highest probability to a neutral action; stochastic exploration can still move. Focus on policy/action distribution, reward shaping and evaluation action mode.
- **Initial checkpoint moves, final idle:** suspect PPO-induced collapse or a training regression.
- **Initial and final idle:** the problem predates this 1M-run; inspect the ReplayBC foundation and observation/action consistency.
- **Both greedy and sampled idle:** native inference may be producing neutral controls or selecting ineffective actions; add an action ID/control trace before retraining.

This test uses **kickoff positions only**. It does not claim anything about other game states. A checkpoint with a few seconds of motion isn't necessarily competitively viable. No auto-promotion and no replacement of Cycle9 or Wavedash.

## Optional advanced commands

In this folder, `py -3.11 student_afk_audit.py --teacher cycle9 --checkpoints all --include-replay` checks every saved checkpoint against frozen Cycle9. Set `--teacher wavedash` to change opponent. **Run only one viewer/audit at a time.**

Send the final terminal output or the JSON report after completion. Fixes must follow the evidence rather than sending more huge PPO runs blindly.
