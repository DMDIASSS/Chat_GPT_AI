# Focused native curriculum

This implements the proposed goal-window practice and staged mechanics in the existing GigaLearn backend. It is a new isolated experiment, not evidence that a native model has beaten update180 or reached SSL. Keep update180 as the playing model while testing.

## Install and run

1. Pause other native training and wait for it to save/exit. Extract the update into `E:\Downloads\Chat_GPT_AI`, replacing code files. Existing models/data are not included or overwritten.
2. Double-click `NATIVE_2_BUILD.bat` to compile the new native stages and verified upstream update. Old runs retain their checkpoints but cannot resume under a changed binary.
3. Double-click `NATIVE_14_PREPARE_WINDOWS.bat`. It reads raw `data\replays\ranked-duels\*.replay`, prepares a NEW `data\isolated\event_curriculum\windows01` corpus, and verifies usable attack/save starts with the actual C++ simulator. This reparses raw replays for event information; the old random-frame `.bin` does not contain the goal/save timeline. This can take longer than the prior parsing pass.
4. Inspect `windows01\diagnostics.json`, `manifest.json` and `cpp_window_audit.*.json`. Missing recorded controls, broken timelines or unreproduced outcomes are reported and skipped. Live replay stages require at least six independent validation matches for each role/color; more raw replays may be needed if reconstruction fails.
5. Double-click `NATIVE_14_FOCUSED_CURRICULUM.bat`. The default full native source is `ranked_duels_train01\checkpoints\3711232`; it trains copies, performs five bounded imitation epochs with validation stopping, then practices one stage at a time. It does not warm-start native MLP weights from the incompatible update180 attention architecture. To start from a different complete native checkpoint, use `--source` on the CLI. The four-file RLBot export is insufficient for a full optimizer continuation.
6. Use `NATIVE_14_PAUSE.bat` and wait for `PAUSED` before closing the window. Resume with the same start launcher. `NATIVE_14_STATUS.bat` reports progress. The updated AFK Improved Viewer/C++ section also has preparation, start, pause and report buttons for these defaults.

Do not start multiple training campaigns together. Existing window corpora/experiment protocols are immutable; use a new run name after changing code, binary, source weights or settings. A rebuilt binary can re-audit the same unchanged prepared corpus into a separate audit file without re-parsing raw replays; changed corpus contents require a new `--prepared` directory.

If startup reports `Stale native library beside executable`, stop native training/evaluation and run `NATIVE_SYNC_LIBRARY.bat`, then restart the curriculum launcher. This verifies and atomically copies the existing `build\giga\GigaLearnCPP.dll` beside the executable; it does not compile, parse replays, change checkpoints or bypass binary identity checks. Builds now refresh this copy even when CMake reports no compilation work. A missing executable/library still requires `NATIVE_2_BUILD.bat`; a DLL held open by another process must be released before repair.

For the inactive native policy, use the new isolated [frozen update180 teacher recovery](SLATER_FROZEN_TEACHER_README.md) with `NATIVE_15_FROZEN_TEACHER.bat`. It requires the actual local update180 checkpoint, verifies its movement, labels states visited by the student and applies native masked teacher imitation periodically. Old campaign 14 is preserved. The update also corrects grounded evaluation orientation and imitation action masks.

## Goal and save windows

The preparer selects 5-, 8- and 12-second sequences before goals. It labels the last ball-touching player on the scoring team as the inferred attacker, skipping apparent own goals. This is not always the official credited scorer. Actual save-tagged events provide defender imitation targets when the parser has those tags. Unmarked hits are not invented saves.

Imitation uses current reconstructed physics and previous controls, confidence-weighted feasible actions, and replay/match-level train/validation/test grouping. Multiple recordings of the same match share a split when metadata provides its game ID. Sampling budgets are spread across sources so the first few matches cannot consume the entire bank. Test labels are not used for training or stage scheduling.

Missing throttle/steer coverage is explicitly rejected instead of being filled with zero. Broken frames, reset crossings and stale inputs reject that view. A ball/car inside the goal mouth before the scored event is allowed; outside-wall positions are rejected. Dodge-label confidence compares effective `(pitch, yaw + roll)` direction so equivalent native yaw/roll encodings are not falsely rejected. Discrete 90-action controls and reconstructed aerial inputs cannot reproduce every original analog input perfectly. Actor/label KL is a fit measurement; physical playback and goals matter more than a near-zero training loss.

For live PPO, the long demonstration is narrowed to a 1-, 2- or 5-second suffix that physically reproduces its goal. Attack cases additionally require attacker contact and must fail to score with that attacker passive. Save cases must concede when the defender is passive. Both Python and native C++ check these positive/counterfactual controls. The frozen opponent replays its inputs while the learner chooses its own actions; all cars and the ball remain dynamic. No ghost positions are teleported into the world.

A save needs an actual learner interception and clearance; surviving a missed/delayed shot is not sufficient. An attack needs learner controls, contact and a scored goal; a reset whose ball was already going in cannot give a free mastery pass.

## Stages and rewards

Order: useful contact → ground scoring → replay attack → replay saves → kickoff → boost pickup → wall roll → wall pop → aerial carry → aerial finish → complete wall-to-air finish → reset acquisition → reset use → reset finish → reset double tap.

The first two stages are mandatory because the supplied native policy was inactive. Boost pickup is rewarded once per episode, not for consuming boost or cycling the same pad. Wall pop requires an actual touch sending a high ball away from the wall. Carry rewards require recent nose contact, close relative speed, airborne control and goalward travel; paid duration is capped. The full wall-to-air stage requires wall interaction, pop, qualified carry and goal in one rollout.

Reset acquisition needs four wheel contacts, underside/ball geometry, spent-to-regained flip availability and RocketSim's actual flip-reset state, away from floor/wall/ceiling. A useful subsequent flip touch gets a small bounded bonus. The larger goal bonus needs a qualified carry before the reset and useful reset use. Double tap additionally requires a high backboard rebound, a later goalward retouch and a goal. Acquiring a reset, landing, proximity to the ball or touching it without follow-through does not earn the finish bonus.

Frozen rivals use the existing kickoff script. The learner stays policy-controlled. The kickoff stage can use one bounded script-imitation warmup on entry, then tests the raw policy against scripted rivals. First contact is a useful drill target, not a guarantee of winning kickoffs strategically.

Default chunks train 500,000 additional learner decisions and save every 200,000. Procedural difficulty grows in 0.25 increments after physical tests pass. Advancement requires ten consecutive successes in varied validation cases for each color and a conservative success-rate check; the configurable streak is 5–15. Replayed cases are grouped by match for confidence rather than treating repeated copies as independent. Every fifth chunk rehearses a previously mastered skill, and all old skills are checked before advancement. Every fifth chunk or successful check also compares against Nexto/update180 in 45-second games, both colors; these screens remain exploratory.

Each difficulty level stops after 30 chunks if not mastered, preserving every checkpoint and reporting `STAGE_BUDGET_REACHED`. Disk-space checks stop before fewer than 10 GiB remain. The trainer does not silently claim mastery, delete weak models or replace the playing model. Longer independent whole-game tests are still needed to establish a stronger generalist.

## Reports

- `data\isolated\event_curriculum\focused_curriculum01\status.json`: latest checkpoint, current stage/difficulty, mastered drills and latest game ranking.
- `chunk_00001\stage.json` and `retention_*.json`: physical outcomes, touches, idle fractions and streak/confidence results.
- `chunk_00001\imitation_fit.json`: actor cross entropy and KL to reconstructed labels on validation rows.
- `data\isolated\native_quality\focus_curriculum\focused_curriculum01\chunk_00005.json`: ordinary match comparison.
- `data\isolated\gigalearn_native\runs\focused_curriculum01_*\training_metrics.json`: actor/critic loss, post-update PPO KL, entropy, speed, idle fraction and touch frequency.

`trusted` in curriculum status means a checkpoint passed drill/retention checks. It does not mean a certified stronger playing model. The playing-model reference remains update180 when available.

## Discord guidance and validation limits

See [the extracted Discord evidence](docs/DISCORD_CURRICULUM_EVIDENCE.md) for authors/dates, the relevant messages and the code decisions they informed. The larger dump was used directly for this pass: staged difficulty, outcome-linked rewards, control reconstruction limits and the need for actual playback checks.

Cloud checks use the user's uploaded weights and synthetic physical traces. They demonstrate native collection, recorded-opponent control playback, model preservation, actor/KL reporting, varied-case checks, and pause/resume mechanics. They do not demonstrate human replay fidelity across the user's 212 files, live Windows/GPU behavior, mastery of these stages or a better model. The uploaded 100,000-row bank's JSON audit is not dominated by idle labels (7.47% overall, 9.70% on ground); its 92 MB binary exceeded the cloud transfer limit, so the original policy's cause remains unresolved.

Validated release: 62 relevant tests passed, a real C++ build completed, 72/72 synthetic attack/save windows passed native outcome/counterfactual verification, and an actual pause/resume continued a saved 20,000-decision native chunk before pausing during checks. The short integration model failed skill checks; no mastery or playing-model promotion was claimed.
