# AFK Improved future work — status after research release

## Which model?

- **Protected starting model:** the *old AutoLeague* Cycle 9 (`50f34d4a3723...`), with the strongest 160-episode tournament result against Nexto, 58.75%. It also displayed strong pressure and unpredictable flicks in visual play.
- **New research contender:** *AFK Improved training cycle 9* (separate run; 25 W / 11 L / 4 D vs Nexto, 67.5% on 40 test episodes). It tied the baseline 16 W / 16 L / 8 D in direct competition. These are not conclusive superiority claims. The Aggressive Research tool can automatically include this checkpoint in common-seed held-out evaluations if its archived `.pt` is still present.
- No newer candidate has earned a verified promotion; default initial policy remains the untouched old Cycle 9.

## The GigaLearn C++ path was not rejected or forgotten

The GigaLearnCPP-Leak repo reports roughly 10x faster experience collection than Python RLGym PPO on the author's hardware. It was **deferred pending compatible checkpoint/observation/action support**. It is not integrated into this release, and nobody has measured throughput on the user's system. Needed before migration: Nexto actor architecture conversion, fixed observation/action shape checks, numerical inference parity, then end-to-end steps-per-second and full evaluation benchmark. Preserve Python as fallback. CUDA training is currently unsafe with the bundled native Nexto TorchScript's baked-in CPU tensor.

## Variable number of cars (1v2, 1v3, 2v2, 3v3, 2v3, 3v2)

**Not implemented**. The current Nexto observation adapter expects exactly two cars and a 131-value layout; increasing team size alone would break the observation inputs. The project would need a multi-car tokenized/attention observation adapter, stable padding/masks, training and rollout changes, car-index/team handling, and goal/game evaluation that accounts for uneven teams. Start with read-only 1v2 simulation to validate correct cars and physics before training. Then progressive 1v1 → 1v2 → 2v2/3v3 → 1v3, using baseline/previous-policy games as retention tests.

## Offensive/defensive tactical behavior

- Keep more of original Cycle 9's aggression/flick variation while improving catches, sharp dribbling turns, shot placement, bounce shots, defensive recovery, boost paths, and kickoff fakes.
- Bumps/demos after shots: compare the downstream goal probability and defensive risk, don't reward raw bump/demo counts.
- Most of these need labeled scenarios, longer outcomes, and more objective metrics. Raw touch-count optimization often incentivizes useless behavior.

## Replay and TAS learning

The Replay + TAS Learning v1 pipeline is a **separate** risky experiment. It uses approximate reconstruction and offline holdouts, not guaranteed action supervision. The TAS inspector can parse frame records but lacks verified exact input-label/state alignment. Only train native policy from TAS after a verified reproduction in RocketSim; don't pretend arbitrary `.data` frames are reliable native Nexto examples. Never let replay imitation replace the untouched Cycle 9 automatically.

## Aggressive PPO experiment in this release

Implemented as **four isolated branches** with larger PPO actor LRs and weaker anchoring, plus common-seed independent evaluations against original Nexto and Cycle 9, all in a new folder. This is a *candidate generation tool*, not an infinite-improvement guarantee or multi-car implementation. Keep the best verified policy separate and expect some variants to be worse; bigger gradients can produce dramatic regressions.
