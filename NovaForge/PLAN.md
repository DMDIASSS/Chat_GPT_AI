# Chronos training plan

## Implemented in v1.6.0

The [Chronos branch](CHRONOS_TRAINING.md) initializes the real deployed actor and shared head, trains a separate critic, and fine-tunes through masked PPO with a frozen initialization KL penalty. Opponents are frozen Chronos/Galactus/Ripple/Nexto and saved learner versions. Full optimizer checkpoints, bounded storage, W&B, initial/current watching, paired screening, reports and native-component/v5 export are implemented.

The [upstream review](UPSTREAM_REVIEW.md) records the five-account inventory, pinned source inspection and compatibility decisions. The shared kickoff-template mutation is fixed. Historical affected kickoff comparisons are not valid policy rankings.

## Next gates, in order

1. **Establish the starting behavior.** Run checks, start chronos01 and watch the permanent initialization with 42. Export it separately for offline v5 comparison. Acceptance: competent neural control on both teams, correct camera/controls, no scripted kickoff overriding either model.
2. **Short reward-driven pilot.** Run 32,768 learner decisions, pause and compare with 39. Inspect goals/concedes, contacts, timeout fractions, per-opponent coverage, goal/potential reward contributions, critic fit and anchor KL. Acceptance: training and frozen self-play work without unexplained loss of starting behavior. Reward or KL alone does not establish strength.
3. **Validate outside the development screen.** Repeat with fresh seeds and longer trials, then full offline 1v1 games on both teams against original Chronos and other bots. Keep all checkpoint hashes and the permanent initialization. Acceptance: repeatable gameplay improvement with uncertainty and no automatic promotion from a small screen.
4. **Tune one learning factor at a time.** Compare actor rates/anchor strength and sparse-goal vs potential shaping at equal wall time. Adjust critic warmup only with value/error evidence. Keep teacher inputs, masks and timing fixed. Acceptance: stronger held-out play rather than larger reward or faster physics alone.
5. **Native multi-game integration.** Select one maintained backend after checking availability and licensing. First load the exact two Chronos components and match observations, masks, delayed action traces, rewards and episode boundaries. Then compare learner decisions/sec, collection/update time, RAM/VRAM and playing strength per hour. Python remains the working reference until parity passes; GigaLearn's raw SPS is not claimed here.
6. **Failure/replay reset bank.** Reconstruct supplied 1v1 replays with an explicit replicar adapter or retain serialized learner failures. Track source provenance and uncertain inferred controls; keep a separate evaluation bank. Acceptance: targeted recovery improves without degrading kickoff and full matches. No automatic raw replay integration is included yet.
7. **Additional opponents.** Byte/Kilobyte/Megabyte require their own ByteObs/ByteAction adapter, timing and model checks. Add only after native feature/logit/control parity. Pulsar remains unidentified and is not a fabricated pool member.
8. **Expand game modes only after 1v1 transfer.** 2v2/3v3 need different entity handling, teammate rewards and testing. Do not silently reuse the 1v1 deployment contract.

## Evidence to send after the pilot

Pause with 36, run 39, and upload the generated chronos01 report ZIP. Include a short description of initial vs current play; launcher 41 can export metrics without rerunning evaluations. Real v5 errors and gameplay clips help distinguish transfer bugs from learning problems.

## Earlier work

The old scratch and teacher-copying experiments remain in the source and their own run folders. Their instructions are in [START_HERE.md](START_HERE.md), [FROZEN_TEACHER_COPYING.md](FROZEN_TEACHER_COPYING.md), [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md) and [ARCHIVE_RESEARCH.md](ARCHIVE_RESEARCH.md). They do not initialize chronos01.
