# Fixed opponents, self-play and evaluation

## Availability checked

The current official RLBot/botpack tree contains Chronos, GalactusV2, Elementv5, NectoFamily and Ripple-RLBot. This is a stronger starting inventory than relying on an older fork branch or a stream image. A botpack entry does not imply that an executable can be run as an in-process RocketSim policy.

| Opponent | Verified public source | Compatibility work still required |
| --- | --- | --- |
| Element v5 | VirxEC/Elementv5; current botpack gitlink fd33e506ffe6a78277eb098a245a1c08ed1f33ed | Extract exact model/observation/action contract and match released actions. It is not assumed to be a trivial scripted bot |
| Necto / Nexto | Rolv-Arild/Necto; official botpack NectoFamily gitlink e5510350299e15a850d4388705ad4ee7dfe0e9ed | Different models need their own observations, stateful timing and action masks. Rust's current Nexto crate is a useful independent inference reference |
| Chronos | KingJake3113/Chronos, 4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa | Source selects AdvancedObsPadded(3), 225 features, 8-tick skip / 7-tick delay, shared 960/960 and policy 960/800/640/640 ReLU. Loadout car_id=22 (Breakout). Verify weights and every feature before native matches |
| Galactus V2 | SoldierDoge/GalactusV2, 217324c2fc516048effe0407595fa61c2ebc6863 | README specifies 258 features, 90 actions, 8/7 timing, shared/policy 1024-unit LayerNorm/LeakyReLU and five ball-prediction samples. Loadout car_id=23 (Octane). Those prediction features must be reproduced, not omitted |
| Ripple | Official botpack Ripple-RLBot gitlink 7ca4273a891ab1d04d001b48cb86f1bc8914aa85 | Optional later diversity, with its own loader and contract checks |

Sources: [official botpack](https://github.com/RLBot/botpack/tree/master/Botpack), [Chronos](https://github.com/KingJake3113/Chronos/tree/4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa), [Galactus V2](https://github.com/SoldierDoge/GalactusV2/tree/217324c2fc516048effe0407595fa61c2ebc6863), [Necto/Nexto](https://github.com/Rolv-Arild/Necto), [Element](https://github.com/VirxEC/Elementv5).

No fresh competitive ranking was measured in Phase 1. Historical human-rank claims and bot-stream MMR are not current human MMR, nor evidence of this new bot's strength. Pulsar/KiloByte availability was not established; do not silently install a different similarly named project. The proposed Element→Necto→Nexto→Chronos→Galactus sequence is a checklist, not a verified ordering.

## Self-play design

Begin with one learner and frozen snapshots, not a population of eight simultaneous learners. Keep a uniformly sampled pool component so a noisy matchup estimate cannot erase opponent diversity. Assign a frozen opponent only when an episode resets; do not change its brain midway through a possession. Never optimize the frozen side's action/log-probability rows.

A later PFSP experiment can combine current self-play, history and verified fixed bots. One candidate weighting within the historical pool is `w_j = epsilon + p_j*(1-p_j)`, where p_j is a smoothed draw-adjusted learner score; this favors learnable close opponents, with a uniform floor. It is a design hypothesis, not claimed to be AlphaStar's exact sampler. Compare it with uniform history first. Retain hard opponents for diagnostic tests without spending the entire discovery budget being shut out by the strongest teacher.

Opponent intent prediction is a later auxiliary task using public past/present state. No privileged opponent action is given to the deployed actor. A privileged training critic would require a separately labeled experiment with ordinary-observation deployment checks.

Primary league reference: [AlphaStar authors' paper](https://storage.googleapis.com/deepmind-media/research/alphastar/AlphaStar_unformatted.pdf). Its scale and results are not a forecast for this laptop.

## Evaluation protocol

- Freeze candidate and opponent files by SHA256 before evaluation; write model, simulator, meshes, hitboxes, action timing, masks, config and seeds into each report.
- Separate training seeds, repeated discovery validation and one final held-out confirmation set. Never select rewards, curricula, checkpoints or search settings using the confirmation seeds.
- Record full game score, per-goal events, elapsed simulation time, kickoff type, side, match outcome and termination reason. Do not count goal-reset episodes as full matches.
- Discovery: paired seeds with swapped colors, regulation kickoff variants and separately labeled open-play/defense/recovery panels. Report center-kickoff advantage separately; it cannot stand in for general play.
- Confirmation: preselect one candidate and one primary frozen baseline, then run 2,000 fresh-seed games with balanced colors (1,000 paired-color blocks). Predefine duration/timeout/draw rules and do not stop early when a graph looks favorable.
- Draw-adjusted score = (wins + 0.5*draws)/games. Estimate a 95% interval using the paired-color block as the sampling unit, with a documented nonzero-width bounded fallback when sample variance is zero. Promote only if its lower bound exceeds 0.5 under the preregistered test. A different claimed confidence method requires its own tests; zero-variance bootstrap intervals alone are insufficient.
- Report goal differential, scored/conceded per simulated minute, whiffs, possession loss after touches and opponent-specific results alongside W/D/L. Repeated checkpoint testing is exploratory; do not treat the best of many uncorrected 95% intervals as confirmation.
- A 10-minute fresh-model pilot is for contact/contract/learning diagnostics. All-draw or all-loss matches against Nexto at that stage cannot establish which reward will eventually produce a stronger bot.
- Final RLBot client evaluation checks latency and sim-to-game behavior independently. Native simulation wins do not certify game-client deployment or ability against strong humans.
