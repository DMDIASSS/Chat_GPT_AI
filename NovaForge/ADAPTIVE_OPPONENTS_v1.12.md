# Train more against opponents that cause concessions

This optional sampler resumes your existing selector06, including its optimizer and frozen Fusion. It changes the training opponent distribution. The reward, expert roster, car body, evaluation schedule and champion-promotion rules are unchanged. It does not train the frozen expert networks.

1. Pause selector06 with 28 and wait for saving. Close watch consoles.
2. Copy the ZIP's novaforge and triadbot folders into the existing Chat_GPT_AI, replacing program files. Preserve .venv, assets, runs and exports. No dependency reinstall or model reset is needed.
3. Run 33_ENABLE_HARD_OPPONENTS.bat once.
4. Run 27_TRAIN_OCTANE_SIX.bat to resume your saved model.
5. After roughly one saved 32768-decision segment, pause with 28 and run 32_REPORT_OCTANE_SIX.bat. Share its report ZIP to inspect weights, exposures and progress.

Launcher 34 disables adaptation on the next resume. The base mix is restored without resetting model weights. If training runs with sampling disabled, its old sampler history is cleared; enabling later starts fresh observations. Configuration changes require paused training and do not edit the checkpoint themselves.

Each first-goal training episode records its opponent, whether a goal was conceded and simulated duration. Rates use concessions per minute, rather than raw losses, so an opponent does not get extra weight simply because it was sampled more often. Up to 128 recent episodes are retained per opponent. Each rate is smoothed with 120 seconds of pooled-rate prior exposure, reducing the effect of a few short episodes. With no observed concessions the base mix remains unchanged.

After every 64 completed episodes, the target mixes 50% base distribution with 50% normalized smoothed concession rates. Probabilities are bounded to 5–30%; the current weights move 25% toward the target at each update. Every opponent stays in rotation. Updates apply at episode resets, including the vector environment's automatic reset after a terminal transition. These are training rates across the existing curriculum resets, not an unbiased full-match ranking.

The optional configuration is opponent_sampling_policy.json. Base config.json remains immutable. Every training session records the exact policy and its hash; configuration changes are versioned under research/sampling_changes. This makes the schedule change explicit while preserving the existing model/experiment identity. Use research-fork first if you want a separate controlled ablation.

The full PPO ZIP stores the authoritative history, weights and counters together with the model. Resuming never reconstructs history from the display file opponent_sampling.json. Existing checkpoints without sampler state begin with the base mix and collect fresh observations. Saved-run backups include the policy/display files; preserve those alongside full.zip. Exact mid-rollout physics/RNG recovery is outside the existing resume contract.

W&B charts include sampling/<opponent>_probability, sampling/<opponent>_concessions_per_minute, sampling/episodes and sampling/updates. The report ZIP includes the policy, current probabilities, estimated rates and exposure counts. It contains no model weights or keys.

Automatic W/D/L checks continue to force an equal number of games against all seven opponents. They bypass adaptive training selection. Future guard reports include per-opponent scores and the complete candidate/champion trials, with checkpoint hashes. A promising candidate still requires fresh confirmation before promotion. Earlier reports that contain only aggregate goals cannot reveal which opponent caused those concessions; this update does not invent missing history.

This is a bounded training curriculum, not proof of improved strength. Inspect the first report, then compare balanced W/D/L results over additional seeds. Sampling may focus on weaknesses caused by difficult curriculum states or imperfect adapters; the probability floor/cap and balanced evaluations help expose that rather than treating training loss rates as final rankings.
