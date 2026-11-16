# Terminal reference audit — 2026-11-16

Primary write-up: https://terminalrl.github.io/rocket-league/
Inspected website source: https://github.com/terminalrl/terminalrl.github.io/blob/392ccf7a3a301776f84c8737e313b7b225ad82b9/rocket-league/index.html

The site identifies Terminal as an RLBot Championship 2026 entry. Its reported performance is the author's evaluation, not an independent reproduction here. The page explicitly says training code and bot weights are not released. The public repository contains the website, viewer and recorded-game data, not the trainer.

Reported method:

- RocketSim v3 (described as Rust), custom vectorized environment, 120Hz physics, eight-tick policy actions, 90-action lookup table.
- 7.1M parameter 1v1 attention policy: d=256, four blocks, eight heads; separate critic. Tokens for self, ball, other cars and all boost pads.
- Sparse scoring/conceding only; approximately ten-second discount half-life.
- Seventy percent replay-state episode starts, fifteen percent kickoffs, fifteen percent random. About 4.3M replay states, rank-gated curriculum.
- PPO, snapshot self-play, optional fading teacher/BC KL anchor.
- Biggest reported gains: scale batch/update, more parallel environments with shorter rollouts, replay-state curriculum and kickstarting. PFSP and main-exploiter leagues did not measurably help their small-batch runs.
- Reported 1v1 budget about 20B agent steps in 46 wall hours on two GPUs; team modes use four GPUs. This is not a laptop training-time prediction.

Useful immediate adaptation: benchmark fixed-total-rollout parallelism (64x256, 128x128, 256x64), keeping 32,768 collected player transitions per update. Correct GAE tail bootstrap is already implemented and tested. Timing selects a hardware setting; it cannot establish equal sample efficiency without longer matched experiments.

Promising separate research: properly validated replay-state resets, particularly states near genuine scoring opportunities, while preserving physics and game-state provenance. They are episode initial conditions, not copied action labels or replay playback. We have not audited a local replay-state dataset for DuelForge, so this release does not silently synthesize a replacement or claim that feature exists.

Do not infer that sparse goals alone, a 7M attention model, or a large entropy coefficient will reproduce Terminal on a GTX 1650. Do not treat tournament entry as independently verified tournament dominance.
