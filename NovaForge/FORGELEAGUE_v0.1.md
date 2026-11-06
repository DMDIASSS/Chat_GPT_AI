# ForgeLeague 0.1 / NovaForge 1.14.0

The chosen hypothesis is that direct, anchored fine tuning of the two native actors can improve useful play more directly than selecting among frozen experts. The project tests an asymmetric critic as an optional accelerator; it does not assume it helps. The new folder is independent of all existing selectors and Fusion runs.

Implemented stages:

1. Native Chronos and Galactus actor training, zero-initialized public-context residuals, timed multi-goal matches, explicit goal/match objective and discount-consistent shaping.
2. Matched ordinary/privileged critic pilot for each family; actors are blind in every evaluation and export. Ordinary training wins uncertainty. No incompatible weight merging.
3. Serial frozen-opponent league, snapshot self-play, rotating curriculum challengers and bounded concession-focused sampling.
4. Full checkpoint/optimizer resume, source/config/lineage records, paired development/confirmation WDL, separate held-out testing, regression halts and protected independent v5 exports.

The next research decisions depend on reports:

- If privileged critics do not improve WDL per training decision and per wall-clock hour, leave them disabled; replicate any promising result across training seeds.
- If both fine tunes repeatedly regress, inspect native action/observation timing and reward returns before increasing training duration. Compare potential-shaped and goal-only objectives in separate forked runs.
- If new challengers expose recurring conceded positions, add a bounded training-only failure-state bank; validate reset fidelity and keep test states separate.
- If a challenger helps one matchup but harms the rest, adjust the training mixture using fixed-panel results rather than adding arbitrary rewards.
- Profile inference, simulation and PPO separately before attempting a native GigaLearn backend. This release preserves the existing float32 frozen-inference compilation and avoids unused two-tick observations. It includes no 10x/100x speed claim.
- Only after reliable 1v1 improvement: integrate additional validated opponents, longer-duration training, 2v2/3v3 feature contracts and an explicitly trained team coordinator. The current v5 Hivemind transport is not team intelligence.

Validation checks cover real actor gradients, critic-only warmup, full checkpoint and optimizer recovery for both architectures, actor invariance to private-input changes, exact initialization logits, causal queued-command reuse, seeded simulation reproduction, multi-goal continuation, potential telescoping, guard uncertainty, complete pilot-to-league transitions and independent exported v5 processes. Tiny CI budgets establish functionality, not playing strength. No live graphical Rocket League match has been run in this cloud environment.

Research precedents: [asymmetric actor-critic](https://arxiv.org/abs/1710.06542), [Learning by Cheating](https://proceedings.mlr.press/v100/chen20a.html), and [AlphaStar league training](https://www.nature.com/articles/s41586-019-1724-z). The proposed combination is a testable project design, not a claim to have invented these methods or proved they improve Rocket League bots.
