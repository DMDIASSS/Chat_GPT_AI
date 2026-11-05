# Learning update v1.5.2

## Install and continue your student

1. Pause with **22_PAUSE_COPY.bat** and wait for the training console to finish. Close any viewer.
2. Extract the ZIP into the parent of your existing chat_gpt_ai folder, for example E:\Downloads. Merge the contained chat_gpt_ai/novaforge source files. Keep .venv, assets and runs.
3. Run **1_CHECK.bat**.
4. Run **32_UPGRADE_COPY_LEARNING.bat** once for existing copy02. This preserves the published student, validation corpus, history and raw demonstrations. It saves copy_upgrade_v152_backup.json, archives the active shard list, clears only the active buffer, and sets the optimizer resume pointer to the published student. Resume does not restart from random weights.
5. Run **21_START_OR_RESUME_COPY.bat**. New copy02 runs already use the corrected defaults; upgrading them is a no-op. Existing runs retain their old profile until you run 32.
6. After two or three completed new rounds, pause; run **27_EVALUATE_COPY.bat**, **30_EVALUATE_COPY_MECHANICS.bat**, then **26_COPY_REPORT.bat**. Send the newest report ZIP. **24** opens the learner camera against scorer. **25** exports the published student for RLBot v5.

## What the reports revealed

At 500,000 collected decisions, the published student was still the 250,000-decision checkpoint. Kickoff screening remained 0 wins / 48 losses / 2 timeouts, with 0.48 touches per trial. Training loss reached about 0.23 while broad held-out loss exceeded 12: fitting the narrow training set was not producing broad skill. The contact gate kept collection focused entirely on kickoff approaches. The small monitoring probe was insufficient evidence of transfer to the separate evaluation starts.

Six aerial-start goals in the mechanics report happened with zero student touches. Goals alone were misleading there. New evaluation JSON and shareable reports retain the old outcome metrics and separately count wins_with_student_contact, wins_without_student_contact and contact_score_fraction. Monitoring selection also uses contact-backed goals for its goal tie-break; historical probes without that count receive no goal bonus. The original raw score fraction stays visible. Even a goal after contact is not proof of an aerial mechanic. Inspect practice success and the clip too.

## Implemented corrections

- Beginner reset probability is now 65% kickoff, 35% spread across the configured other scenarios. Zero-weight categories stay disabled. General practice is no longer locked behind a contact gate. This is an episode probability, not a guarantee of equal label counts.
- From the second collection round onward, about half of episodes begin with 1–60 student decisions (up to two seconds) before a frozen teacher takes over. This runs during the beginner stage too. The student prefix is not labelled or rewarded as teacher behavior. Teachers then drive on the reached state; this is takeover collection, not full per-frame DAgger. Takeover episodes continue beyond first touch.
- Only 65% of beginner kickoff teacher episodes are cut at first touch; the rest can show post-contact play. The teacher stays frozen throughout.
- Two fitting epochs per fresh round and learning rate 0.0001 replace ten epochs and 0.0003 for new/upgraded runs. This reduces reuse of a narrow buffer and excessive confidence; it is not a demonstrated match-strength improvement yet.
- A new **scorer** ground baseline approaches behind the ball and drives toward the opponent goal. It scored on both team sides from a controlled shot start in RocketSim. It is not a strong neural bot. The old **scripted** chaser is preserved so historical monitor and evaluation numbers remain comparable.
- Beginner opponents default to scorer. Once the contact gate opens, opponents are sampled per episode from scorer, Nexto, Ripple, Chronos and Galactus. Configure copy.bootstrap_opponents and copy.general_opponents in the paused run config; use comma-separated supported names. Teacher action sources remain the four frozen models. Per-shard metadata records kept_by_opponent and kept_by_scenario. Reports aggregate the active collection counts and teacher takeovers; W&B records teacher collection decisions/second including setup and shard serialization. This is not raw physics SPS or an end-to-end learner throughput measure.

Validation remains the existing fixed separate teacher corpus against legacy scripted. Changed opponents and reset mixtures must be labelled when comparing new training runs. Launcher 27 includes both old scripted and new scorer; launcher 30 now uses scorer, so its numbers are a new opponent cell, not a continuation of the old mechanics cell.

## Kickoffs, 271 and cycle9

Teacher adapters and the student use neural actions without a scripted kickoff override. Watching and exporting the current student also keeps that behavior. No automatic kickoff assist is enabled by this update. A future optional assisted comparison must report its assist flag and stay separate from the unassisted learning benchmark.

Treat the user's model **271** as the reference to preserve and **cycle9** as the design reference. The repository contains older cycle9 PPO scripts with alternating frozen opponents, team-side balancing and a frozen-policy KL anchor. This update does not load or overwrite either model. Exact files/feature contracts for 271 must be identified before importing it or calling it a verified baseline.

## Speed and the native backend

NATIVE_5_TRAIN.bat launches GigaLearn_Project/Native_Backend/native_setup.py with 64 games, 32768 steps, ten iterations, device auto, width 256 and depth 3. That referenced backend is absent from the inspected repository; the launcher alone is insufficient to reproduce its inference, action timing, reward normalization, checkpoint format or SPS counter. This ZIP does not claim to integrate it or reach 1M SPS.

Next native integration gate: obtain that backend source/build configuration, trace the same states/observations/actions/rewards through Python and native code, then batch teacher inference and benchmark end-to-end learner decisions per second including fitting/checkpoint time. Preserve frozen teacher hashes and disabled kickoff overrides. Compare skill gained per minute and per decision against the corrected Python path and 271; raw physics SPS is a separate number.

See [the plan](PLAN.md) for follow-up experiments. These changes correct concrete data and training problems; they do not establish that the student can beat its teachers.
