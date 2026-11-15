# Offense continuation 0.6 — scoring outside kickoff and useful movement

Requires the complete AttentionForge Skills 0.5 project and its trained `runs/skills01/latest.pt`. This is an in-place program update; it does not include or overwrite runs, models, environments, CUDA libraries, credentials or exports.

## Install and start

1. In the existing trainer press Ctrl+C once. Wait for PAUSED_AND_SAVED, then exit its menu with 0. Close trainer/watch/menu Python processes before replacing the native PYD.
2. Extract this ZIP into `E:\Downloads`, merging `chat_gpt_ai\attention_skills` and replacing the included program files.
3. Open **OFFENSE.bat**, choose **1**. On first start it copies the latest completed `skills01` into **attack01**. The actor/critic parameters, Adam moments, optimizer step values, learning rate, RNG state, history opponents and learning counter are inherited. It does not rerun the ground-driving warm start. An existing attack01 is resumed, not overwritten or silently re-forked.
4. Training continues until paused. Use Ctrl+C or **OFFENSE_PAUSE.bat**; SKILLS_PAUSE.bat addresses the original skills01 run. Only one trainer should run on this laptop.
5. To inspect progress, pause and use this menu: **2** watches open play against the exact pre-update parent; **3** watches mixed kickoff positions; **4** creates a report; **5** exports the latest PT/CFG and v5 TorchScript LT/TOML; **6** runs longer balanced scenario panels. **8/9** watch/export the pinned open-play candidate, explicitly labeled unverified. **10** runs isolated finishing/jump/flip/recovery drills on fresh seeds.

The existing SKILLS.bat still addresses the original skills01. New W&B tracking uses a new run ID under attack01. Its transition counter starts at the parent's count; `attack/new_transitions` records experience added in this phase.

## Training changes

The parent already controls the ball, so this phase emphasizes goal completion rather than rediscovering contact. The architecture, Octane body, 90-action table, public observation layout, 120Hz physics, eight-tick decisions and one-tick action delay are unchanged.

The native **attack_v1** profile defines these versioned constants:

- Goal/concede: **+20/-20**, including ordinary goals without any mechanics.
- Actual contact: **0.1**. Positive forward approach: **0.3 per simulated second**, multiplied by how well the car's forward direction points toward the ball. Reverse driving can still earn goal and contact rewards; there is no blanket reverse penalty that would punish necessary defense. It simply does not earn this forward-approach bonus.
- Touch strength retains the prior 0.5-scaled AdvancedTouchReward-style ball acceleration term.
- **Aimed-shot improvement:** on an actual touch, reward `max(0, q_after - q_before)`. The bounded quality proxy projects the ball toward the attacking goal plane, accounts approximately for gravity/one floor bounce, and discounts trajectories outside the posts or above the crossbar. Speed scales the signal; a further small 0.1*q touch bonus replaces the previous loose velocity-toward-net bonus. This is an unobstructed geometric proxy, not a goalkeeper-aware probability or a complete RocketSim prediction. Wall bounces, spin and player interference can defeat the approximation; actual goals remain the primary outcome.
- **Useful jump launch:** 0.025 on a first-jump edge toward a nearby elevated ball, with a two-second reward cooldown. Holding jump does not keep paying. Flat-ball jumps, jumping away, and merely staying airborne do not earn it.
- **Air approach:** up to 0.15/s only while airborne and moving toward a nearby elevated ball.
- **Air/jump contact:** up to 2.0 for actual elevated contact, scaled by height and flight time, paid once per flight. There is no continuous reward for height or airtime alone.
- **Useful flip acceleration:** up to 0.12 for a new flip that accelerates the car toward a sufficiently distant ball while aligned forward, with a three-second cooldown.
- **Backward-to-forward flip recovery:** 0.3 after a car starts moving backward toward a distant ball, backflips, rotates toward that direction and lands upright with useful forward speed. Nearby reverse positioning is not penalized. This detector measures a useful half-flip-like recovery outcome, not the exact textbook input sequence.
- The prior distinct-event goal combo remains capped at 1.5 and is paid only at a real goal. Repeating or alternating already-seen event types does not stack it.

The profile constants are implemented and tested in native/attack.h and native/core.cpp; metadata in the run configuration describes the profile, rather than making every native coefficient a live JSON tuning knob.

The entropy coefficient has a floor of 0.008. The early ground-driving auxiliary loss is disabled in this phase because it conflicts with jumping/flipping; at your reported 13M steps it had already faded to zero. No learning-rate increase or architecture reset is applied.

## Practice and reset distribution

Training resets use **30% conventional kickoffs**, spread uniformly over all five real spawn positions, **35% finishing positions**, **20% elevated jump-touch situations**, and **15% long backward-recovery situations**. Thus center kickoff is approximately 6% of resets. Both teams are controlled by the learning policy or its existing history opponents during PPO; neither receives a hidden scripted kickoff.

A small, temporary **training-only mechanics rehearsal** helps discover multi-step moves. The program generates half-flip, forward-flip and jump-touch demonstrations in RocketSim and keeps only physically successful trajectories, stopping labels at the first successful completion so it does not teach an idle tail. All labels obey the actual action mask. A 32-example auxiliary minibatch has initial weight 0.02 and fades to zero after 5M *new-phase* transitions. The cache is stored atomically in the new run, with success counts in movement_rehearsal.json. If no demonstrations validate, the program reports that and continues the reward-based trainer without pretending the tutor succeeded.

These demonstrations supply training labels; **watch, match evaluation and both exported adapters use the network alone**. They do not execute the demonstrations, force throttle/jump, or inject maneuver sequences during play. Rehearsal success proves that the demonstrations and detectors work, not that the student already knows those mechanics. Temporary auxiliary training and larger diagnostic panels can cost throughput; no speedup is claimed.

## Evaluation that exposes kickoff-only gains

Every 500k new transitions, the trainer checks retained ground contact and isolated finishing, jump-touch, forward-flip and recovery execution. The isolated probes park the other car; they measure execution, not competitive strength. The baseline probes are recorded before the first offense update.

Every 2M new transitions, it evaluates **each of these contexts separately** against the frozen pre-update parent:

1. Center kickoff.
2. Left diagonal kickoff.
3. Right diagonal kickoff.
4. Left off-center kickoff.
5. Right off-center kickoff.
6. Open play, with no kickoff resets.

Automatic panels use 40 games/context, 60 seconds; menu 6 uses 100/context, 90 seconds. Kickoff cars receive equal 33 boost and mirrored official spawn poses. Each seed is played on both colors. The same context is re-created after goals; these are controlled scenario panels, not regulation tournament matches. Reports preserve initial poses, raw goals, elapsed time since each reset and touch counts. Goals within five seconds of a reset are reported separately from later goals. That timing split is a diagnostic heuristic, not proof that a later goal is tactically sophisticated.

The summary displays open-play score and the non-center mean explicitly. A center-only advantage warning prevents describing a center boost race as broad scoring progress. New attack training uses a low native-seed band; automatic match panels use a separate high seed band. Explicit reproducibility/test seeds are labeled separately.

Promising actors are stored in **immutable, actor-only match_pins**, with exact model/file hashes and evaluation references. Improved pointers are maintained per context. Pinning is exploratory: it does not certify or automatically promote a champion. These actors are watchable/exportable but are not full optimizer-resume checkpoints. They are not removed by history rotation. There is no silent substitution if a pin is missing. The report includes a pin inventory; it does not upload weights.

Contact collapse uses the existing bounded archive/restore recovery. Two consecutive panels with macro score below 40%, or open-play score below 25%, pause training; the parent, pins and latest run remain available. These are pragmatic regression thresholds, not statistical guarantees. Formal confidence intervals in small/repeated panels are deliberately conservative and do not adjust for repeated model selection.

## What was verified and what remains open

See OFFENSE_VALIDATION.json. Native reward and scene tests, exact fork preservation, legal successful demonstrations, snapshot-safe pins, pinned watch/export and continuation/resume were exercised. The Windows native build passed. The test server has no CUDA GPU or Rocket League client, and your actual 13M-step weights were not uploaded.

A short pilot using our earlier learner retained strong basic contact. It also showed losses on a diagonal kickoff, which the new panels correctly exposed. Short pilots did **not** establish that the student had learned half-flips/aerials or become a stronger match bot. This update gives it targeted signals and valid practice, and measures the requested outcomes; those outcomes still require training and evaluation on your PC.

The old parent and its original training remain intact. Do not erase them to install this update.
