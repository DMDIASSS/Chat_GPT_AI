# Frozen update180 guidance for the native student

The supplied native 3711232 policy already assigns roughly 90–92% probability to the idle action in simple touch starts. It stays idle in physical playback; original Nexto drives and scores in the same starts. The next two Windows checkpoints also failed all 32 touch checks. A subsequent longer user run recovered through PPO: checkpoints 10089408, 10619808 and 11152448 passed 32/32 touch checks, with average idle fractions about 20.7%, 7.9% and 5.7%. This demonstrates that the existing native training can recover; it does not identify a defect in GigaLearn itself or prove that replays caused the original collapse. Preserve the recovered student when adding teacher guidance.

Two application errors are corrected: replay imitation now uses the same feasible-action mask as inference, and grounded Python drill starts face along the floor like the C++ starts. Previously those evaluation cars were tilted upward toward the ball. The original policy remains idle with either orientation, so this mismatch alone does not explain the collapse. Warmup episodes now finish after an active learner touch, with a bounded stationary penalty near the ball and a first-contact reward.

## Install and run

1. Pause the older curriculum using `NATIVE_14_PAUSE.bat` and wait for `PAUSED`. Stop any other native campaign.
2. Extract this update into `E:\Downloads\Chat_GPT_AI`, replacing code files. No model/data files are included.
3. Run `NATIVE_2_BUILD.bat`. A backend content fingerprint forces compilation of changed code even when ZIP timestamps are older than existing object files. The DLL is refreshed and checked after the build.
4. Run `NATIVE_15_FROZEN_TEACHER.bat`. It starts the separate `focused_teacher01` campaign from a copy of the latest complete native checkpoint recorded in the paused old `focused_curriculum01\status.json`. It skips repeating the initial human-replay imitation warmup, preserving the current model's progress. On later starts it reuses the new campaign's pinned source rather than reading a different old-run checkpoint. It requires the real `data\isolated\mechanics_curriculum\selected7_mechanics01\update_000180.pt` and stops if it is missing; it does not silently substitute Nexto. The existing `windows01` replay corpus is re-audited under the new binary without re-parsing the raw replays. Old audits, experiments and checkpoints are preserved. Skill stages are verified again under the corrected evaluator rather than copying mastery claims across changed code.
5. Pause using `NATIVE_15_PAUSE.bat`; resume with the same start launcher. Use `NATIVE_15_STATUS.bat` for progress.

The attention teacher .pt cannot be copied directly into the native 230-input/90-action MLP. Its weights stay frozen; it supplies current-state action distributions through the same attention observation path used for playing. Native policy and shared-head optimization remain in C++. Only the bounded demonstration collection/playback is Python.

## Guidance and checks

Foundational contact, ground scoring and kickoff receive help every chunk; later stages receive teacher rehearsal every third chunk. Each guided chunk collects 48 independent six-second episodes, half teacher-driven and half student-driven, including ordinary-play starts. These are demonstrations separate from learner PPO. The demonstration rival uses frozen update180; native PPO still uses compatible frozen native rivals. Rivals use scripted kickoff; the learner has no kickoff control override.

The teacher is queried on states actually visited by the student, even when the student is inactive. Recorded controls are projected to feasible native actions by physical similarity. For a grounded non-jump action, irrelevant aerial pitch/yaw/roll are ignored, preserving useful throttle/steering/boost instead of dropping the teacher's probability mass. Valid native actions retain their exact IDs. Legitimate idle teacher choices remain allowed; no movement override hides a collapsed policy.

Episodes are split by group into train/validation/test. Teacher labels use only the current state and prior controls. Test labels never enter optimization or validation stopping. Collection records actual teacher movement, touches and goals, and refuses an entirely inactive teacher before using its bank. It verifies the teacher and source checkpoint were unchanged.

Five bounded imitation epochs with validation stopping run before PPO and after a completed PPO chunk, limiting forgetting. Pause requests skip the final refresh and are checked between collection episodes and imitation batches. The new campaign reports both actor loss and teacher KL, then performs the existing greedy physical drill checks and whole-game screens. Three consecutive warmup checks with over 98% idle time stop as `PERSISTENT_IDLE` instead of wasting further chunks. Failed skill checks do not advance stages or promote a playing model.

Reports are under `data\isolated\event_curriculum\focused_teacher01\chunk_00001`:

- `teacher_bank.json`: actual teacher/student activity, displacement, touches, goals, grouped splits and checkpoint identities.
- `teacher_before.json` / `teacher_fit.json`: masked actor cross entropy, teacher KL and idle argmax rate before/after the chunk.
- `stage.json`: raw learner physical touch success and idle fraction, both colors.

Native training logs contain `SLATER_TEACHER_BC_PRE`, `SLATER_TEACHER_BC_POST`, and `SLATER_TEACHER_REFRESH_COMPLETE`. Faster collection and smaller KL do not certify competitive strength. Keep update180 as the playing model until fresh-seed whole-game comparisons establish an improvement. Update180 may not be an expert at every advanced mechanic; teacher rehearsal cannot replace physical success checks.

Cloud validation uses the uploaded native checkpoint and original Nexto as the available attention teacher. The actual update180 checkpoint is on the user's PC and its movement on both colors must be verified by the local collection report. No Windows/GPU or update180 result is claimed from these cloud tests. The relevant suite passed 77 tests.

The native integration build completed; the full guided runner executed both pre/post teacher refresh, passed 96-state C++ parity and 10/10 fresh simple touch cases, and left the original checkpoint unchanged. A separate 24-episode collection gave the teacher 12/12 touched episodes and the initial student 0/12; its native recovery passed 8/8 fresh touches with idle time near 2.8%. The very short four-game screen against Nexto remained 0 goals scored (8 conceded before versus 4 after); it is not a competitive-strength certification. Pause saved progress and skipped final refresh. These are simulator integration checks, not mastery or an update180-trained model.
