# AFK → GigaLearn research curriculum, implementation roadmap

This document is a proposed long-term **experiment program**, not a claim that all modes currently work or that performance will grow monotonically.

## The founding model question

Use **two separate approaches**. (A) Native Nexto lineage (`Cycle 9`, `Wavedash`, `previous_afk_cycle09`) stays in AFK Python for comparisons, RLBot exports and native `.pt` optimization. (B) New GigaLearn policy starts from scratch or resumes a **GigaLearn** `.lt` checkpoint; it uses a different action/observation/network design. Before merging these we need a validated teacher/student distillation adapter, which does not yet exist. No copying weights between formats.

## Recommended schedule with assessment gates

| Stage | Target | Mechanism | Current readiness |
|---|---|---|---|
| 0 | Infrastructure | GigaLearn build, CUDA, RocketSim, safe stop, resume | Build/run worked previously; new research patches need Windows test |
| 1 | Basic ball control + scoring | C++ 1v1 balanced PPO, random/kickoff starts | Research profile exists, physics needs test |
| 2 | Directed shooting + aim | shot events, touch acceleration, ball-to-goal velocity; develop goalie-target tests | Partial reward proxy only |
| 3 | Defense + positioning | saves, goals conceded, random starts 1v2 and 1v3 | Configured team counts but no custom defense-pressure state setter |
| 4 | 12–24 variants | small LR, seed, reward and curriculum perturbations | Reproducible plan, isolated training; tournament evaluator not complete |
| 5 | Special mechanics | recovery, wavedash, speedflip, wall-dash at 120 Hz, power shots, air dribble | Recovery/air/power *proxy rewards*, frame-precise controllers pending |
| 6 | Human replay dataset | action reconstruction, confidence filtering, train/val split, convert to same GigaLearn observation/action space | AFK dataset exists; no GigaLearn training adapter |
| 7 | Verified TAS | actual inputs + frames + reproducible state -> control cloning, action-rate alignment | TAS audit only; direct learning blocked |
| 8 | Native teacher distillation | choose Cycle9 offensive/ Wavedash defensive decisions in matching state distributions | No bridge; should be independently verified |
| 9 | Teamplay | 2v2, 3v3, 2v3, 3v2 with teammates/opponent entity attention & role policy | GigaLearn shared-policy and historical-policy self-play can be configured; roles not implemented |
| 10 | Undermanned defense | 1v2, 1v3, multiple frozen Nextos, robust clears and shadow challenges | shared policy multi-car exploratory modes; frozen Nextos pending |
| 11 | Consolidation | mixed scenes, specialist performance, historical opponents, holdout evaluation | Evaluation automation pending |

### Never run TAS-only learning for months at the start

Your source `.data` TAS files appear to contain controls, but the exact analog/button mapping, starting state and match engine state alignment must be verified. Long imitation without validated labels can make a policy worse. When ready, blend short specialist BC bursts with PPO, reference-policy anchoring, and independent games. Similarly the current Ballchasing replay-to-Nexto dataset is not directly consumable by C++ GigaLearn.

### Evolution League validation protocol

1. Plan 12 or 24 seeds/parameter combinations.
2. Train each independently from an **identical GigaLearn parent checkpoint** if doing small comparative changes; baseline from scratch is allowed but less controlled.
3. Use paired seeds and colors in the future native evaluator; prevent near-identical deterministic starting states from dominating.
4. Short screening → 4–6 finals → robust round-robin → heldout baseline Nexto and full-match RLBot spot checks.
5. Keep non-transitive counters and diverse specialists even when they don't rank first.
6. Promote only when both performance and safety requirements pass. Never select solely on reward or training loss.

### Air and ball-speed labs: avoid reward hacking

- **Air control:** reward supervised air-dribble/passing outcomes, possession/recovery and useful goal pressure, NOT merely any airborne ball. Current proximity-and-altitude shaping is intentionally weak and is only a first controlled experiment.
- **Power shot:** prioritize faster *useful* shots (velocity to opponent goal and successful on-target shots). Do not reward shooting into own goal, no infinite wall bounce loops, always cap episode duration.
- **Bumps and demos:** measured post-shot save prevention and useful interference—not raw demo counts.
- **Mirror**: RLBotPack's MirrorBot manipulates mirrored car state and controller inputs; useful as a stress-test reference but not a fair gameplay opponent. A RocketSim symmetry curriculum requires independent development.

### Performance expectations

Prior native Nexto tournament: Cycle9 58.75% vs original Nexto in 160 first-goal episodes, Wavedash 55%. `previous_afk_cycle09` achieved 57.9% in a different 120-episode test and tied Cycle9 50.8% head-to-head. They are not directly compatible with GigaLearn `.lt`; don't claim a transferred starting model. Your new GigaLearn policy ran about 25k timesteps/s and saved checkpoint 4,562,496, but competitive level is not yet known.
