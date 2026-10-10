# AFK Improved — Multi-agent and curriculum roadmap (not implemented)

## What is genuinely available now?
- 1v1 Nexto / self-play with the saved Cycle 9 policy, AutoLeague and checkpoint gating.
- Native model uses Nexto's attention-based architecture. This is not a new attention mechanism.
- The current `native_nexto.Match` creates `FixedTeamSizeMutator(blue_size=1,orange_size=1)` and assumes exactly two players.
- **Hard blocker:** `nexto_teacher.encode_v2_state` explicitly requires exactly one blue + one orange (shape 131), and `NextoTeacher(...).obs_builder` uses `n_players=2`. Simply increasing `FixedTeamSizeMutator` will fail or train incorrectly.

## Order for actual team support
1. Expand state encoder and Nexto observation builder to 2–6 total cars. Validate shape, entity indices, masks, boost timers, and blue/orange inversions for every roster. Verify original Nexto output behavior is sensible for a 2v2/3v3 configuration before PPO.
2. Rewrite `Match` to map one controlled learner, optional teammates, and N opponents; use stable sorted agent IDs and per-player previous controls. Define independent policy assignments: frozen Nexto, historical snapshot, current learner, random opponent.
3. Use curriculum of formats: 1v1, 2v1, 1v2, 2v2, 1v3, 3v1, 2v3, 3v2, 3v3. Test mirrored team assignment and kickoffs. Do not train against 2–3 Nextos until this is validated.
4. Define zero-sum team outcome reward with role-independent credit assignment; observe overcommit count, goal-exposure time, last-defender danger, recoveries, boost picked safely, useful pressure, demos, and passes. Avoid rewarding passive retreat or random 50/50 touches.
5. Add opponent sampling mix: Nexto + past snapshots + self-play; train variable roster with replayable seeded scenarios. Avoid letting a 1v3 agent forget 1v1 competence; interleave 1v1 and 2v2.
6. Explicit kickoff variants: fast, delayed, fake, teammate corner, boost-abandon, defensive shadow. Evaluate 5–10 second post-kickoff outcomes including ball position and goal safety.
7. Head-to-head gate per mode, fresh seeds, first-goal and five-minute match metrics. Require no material regression in 1v1 before promoting to primary verified best.
8. Only then test 1v2 or 1v3 against Nexto and compare against Slater/Rift if runnable opponent implementations are available. Online videos alone do not verify broad superiority.

## Replay curriculum (separate project)
- Native Nexto input needs exact state-to-observation match, plus reconstructed controls (RLCarInputSolver or comparable tools) and confidence filtering.
- Start with diverse high-rank 1v1 for dribbling, fake challenge, pressure. For 2v2/3v3, curate separately (rotations, defensive role and coordinated kickoff). Zen clips may be specialist examples, not sole dataset.
- Train on a copy with KL preservation; validate on clean holdout and fresh RocketSim tests. The existing downloader/audit DOES NOT perform imitation learning.

## GigaLearn speed claim
Reported ~10x collection throughput is attractive but not guaranteed on the user's computer. PPO step/s and wall-clock improvement also include inference, learning, evaluation, and GPU availability. Direct checkpoint migration is not implemented.
