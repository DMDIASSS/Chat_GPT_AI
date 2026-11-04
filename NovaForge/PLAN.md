# Implemented work and next experiments

**v1.5:** correct transition labels and eliminate previous-action shortcuts; start fresh `copy02`; bootstrap first-touch approaches, then expand the curriculum; select published models using student kickoff monitoring plus copying loss. Auto-find/open RLViser with a checked Windows camera build, preserve Forge dashboard links, and add mechanics/coverage reporting. See [the correction](COPY_CORRECTION_v1.5.md) and [camera setup](RLVISER_CAMERA.md).

**v1.4:** [LibTorch .lt + RLBot v5 export](V5_EXPORT.md), supported actor packaging, and the requested `chat_gpt_ai/novaforge` ZIP layout. Shared simulator returns mildly weight imitation labels; the original teachers’ reward functions are unavailable.

**v1.4 copying:** continuous frozen-teacher copying with fresh demonstration rounds, fixed separate validation episodes, balanced teacher losses, previous-action dropout, and teacher takeovers from student-reached states. Best validation checkpoints serve watch/export, while latest optimizer checkpoints serve resume. Launchers **21–27** and [FROZEN_TEACHER_COPYING.md](FROZEN_TEACHER_COPYING.md) cover the workflow. Supervised agreement is evaluated separately from actual playing strength.

**v1.3:** one-click progress report ZIP with offline charts, selected config, opponent/mechanics trends, PPO metrics and checkpoint hashes; earliest/current paired comparison helper; PPO CSV retention across resumes. Report sampling units distinguish learner decisions from raw physics and teacher work. Technical archives informed the interpretation and next experiments in [ARCHIVE_RESEARCH.md](ARCHIVE_RESEARCH.md). See [PROGRESS_REPORTS.md](PROGRESS_REPORTS.md) for the feedback workflow.

**v1.2:** mixed-training launchers now support continuous training until pause and an optional W&B dashboard. The tracking integration reuses the SDK's local login, keeps the online run ID across resume, reports opponent/mechanics/PPO metrics, and exposes the dashboard link in local status. See [WANDB_AND_CONTINUOUS.md](WANDB_AND_CONTINUOUS.md).

**v1.1:** Chronos and GalactusV2 now have working CPU simulator ports and join Nexto/Ripple in the diverse league. Mixed teacher collection is implemented. Native C++ feature/mask/network comparisons and short real training checks pass. The remaining work for these ports is broader trajectory/live validation, forecast comparison and the unavailable world-contact-normal exception; see [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md). Pulsar stays out until a deployment identity/checkpoint is established.

## Included in this ZIP

| Feature | Implementation | First test |
| --- | --- | --- |
| New student | 100 team-relative features, 276 discrete controls, separate 256×256 policy/value MLPs | Core smoke and simulator/live observation parity tests |
| Self-play league | Frozen latest policy plus a 12-member active history, sampled once per episode | Smoke exercises a saved snapshot as a real opponent |
| New strong trainer | Ripple v1.1 ONNX adapter with original action queue | Teacher doctor and delayed-control tests |
| Old reference trainer | Nexto neural policy, held at eight ticks | Both-side actual model tests |
| Mechanics practice | Seven reset types, varied difficulty and per-worker success estimates | Both-side simulator resets and metrics tests |
| Teacher imitation | Actual executed controls; incompatible labels filtered; episode-disjoint validation | Collection → BC → PPO initialization integration check |
| Replay training starts | RLGym-tools parser → filtered serialized 1v1 states → new teacher rollouts | Serialized reset bank exercised in RocketSim; raw file parse still needs a user fixture |
| Experiment evidence | Config/provenance, component rewards, PPO CSV and seeded paired screening | Short evaluation report, timeout accounting |
| Deployment | TorchScript actor with hash/contract metadata and RLBot v5 launcher | Export/PPO action parity and live-state feature parity; live match still needs Windows testing |
| Operational controls | File lock, full optimizer checkpoint, atomic latest pointer, pause/resume | Two-worker real PPO smoke with resume |
| Continuous training and W&B | Repeat PPO segments without resetting the model; reuse online tracking ID and show status/link | Real SDK offline logging, multi-segment mixed run, pause and resume; online credentials checked on the user's PC |
| Shareable progression evidence | Selected metrics/config ZIP, offline charts, matched teacher cells and earliest/current paired evaluation | Export allowlist/secret exclusion, disjoint windows, evaluation ownership and CSV retention tests; real report and checkpoint comparison |

## Suggested experiment order on this laptop

1. Run install, tests, smoke and teacher checks.
2. Collect 20k Ripple decisions against Nexto; pretrain five epochs.
3. Train `laptop01` for 100k decisions and screen it against its BC initialization.
4. Extend a successful run by 2M decisions. Preserve reports even if it gets worse.
5. Compare a scratch run and a BC run at the same budget; then compare plain self-play and trainer mixing.
6. Add a few verified 1v1 replay files. Compare teacher demonstrations from replay starts with the normal reset distribution.
7. Export promising checkpoints and play multiple full offline RLBot matches on alternating team colors against the named bots.

Keep evaluation seeds separate from collection/training seeds. Use a second new evaluation seed set before concluding that a change helped. First-goal simulator scores are preliminary. A mechanics proxy, BC accuracy or shaped reward can increase while playing strength falls.

## Next additions, in order

1. **Windows transfer fixes.** Use the user's live clips and errors to fix packet timing, coordinate conversion or launcher issues before increasing model complexity. Acceptance: the same known-state features and controls agree across simulator and live adapter, then several uninterrupted RLBot games.
2. **Chronos port transfer validation.** The v1.1 implementation matches the native feature/mask fixtures and C++ network logits. Extend comparison to long trajectories, demos, collisions and live matches. Check sensitivity to player-slot randomization and the unavailable contact-normal exception.
3. **Galactus port prediction validation.** The v1.1 implementation matches native features with identical prediction samples and C++ network logits, including tick-eight/delay-seven scheduling. Compare full cached RocketSim forecasts with the native internal tracker and live prediction packets over collisions and goal transitions.
4. **Hard-example replay bank.** Store actual learner failures and sample a bounded portion of training resets from them, keeping a separate untouched evaluation bank. Acceptance: recovery on the targeted failure improves without degrading kickoff/full-game screening.
5. **Skill-specific teachers and a goal-conditioned policy.** Condition on an explicit task and sample actual mechanics demonstrations. Acceptance: aerial/dribble/recovery proxies and held-out match outcomes both improve. A high-touch counter alone is insufficient.
6. **Reachability-grid experiment inspired by the public Pulsar research.** Begin with reset-cell mastery using actual success, then evaluate a contrastive critic as a separate algorithm. Acceptance: equal-compute improvement on held-out starts and first-goal/full-match evaluation; no claim of reproducing Pulsar without matching its system.
7. **2v2 / entity attention.** Change the feature contract, add teammate roles and random player ordering, introduce team rewards, and retrain. Acceptance: rotation/pass/defense metrics plus 2v2 match evaluation. The v1 weights would not be compatible.
8. **Native GigaLearn rollout path.** Port only after the Python loop is stable. Acceptance: trace parity first; then measured end-to-end decisions/sec and match strength per training budget.

After your first test, the most useful evidence is the smoke/doctor JSON, BC loss/accuracy, PPO throughput, evaluation outcomes with timeouts, and a clip of a repeated failure.
