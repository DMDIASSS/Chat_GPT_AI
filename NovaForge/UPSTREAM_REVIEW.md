# Upstream review for the Chronos student

Review date: 2026-11-05. The user's five account links were inventoried with public repository search, paginating VirxEC's second page. The search returned **233 repositories**: Rolv-Arild 41, RLBot 44, SubparN0va 3, VirxEC 104, ZealanL 41. Root README files were retrieved for **203**; **30** had none at the common root names tried. This is a catalog and relevance review, not a claim to have read every line of all 233 repositories. See [the full inventory](upstream_inventory.json).

For deeper inspection, **19 source archives** were downloaded at immutable commits. RLBot/botpack was checked as a catalog rather than downloading the entire model collection. Source review focused on training updates, observation/action contracts, checkpoint loading, opponent selection, export and packet timing. The installed pinned RLGym/rlgym-compat/SB3 runtime source was also read where it drives this implementation. Exact commits and GitHub-reported license labels are in [upstream_pins.json](upstream_pins.json); missing metadata is not a license grant.

## Decisions that changed this implementation

| Source | Read and finding | Decision |
| --- | --- | --- |
| KingJake3113/Chronos | RLBotMain.cpp model sizes, Chronos obs/action code and client scheduling; 225 features, 90 actions, LayerNorm/ReLU, 8-tick decisions and 7-tick delay | Initialize the actual policy and shared head directly. Keep the mirrored feature/action convention and the deployed timer ordering. |
| Rolv-Arild/rocket-learn | PPO and Redis worker pretrained-agent / past-version selection | Mix fixed pretrained opponents with latest and historical frozen learner snapshots. Do not mutate an opponent during an episode. |
| Rolv-Arild/Necto | Pretrained policy and observation/action documentation | Nexto remains a separately adapted frozen opponent. Its feature/action interface cannot initialize a Chronos network by renaming weights. |
| Rolv-Arild/replay-pretraining | README and reconstruction/pretraining flow | Imitation is a starting point; compounding error and ambiguous inputs remain problems. Do not substitute action agreement for reward-driven learning. No code from this GPL project is vendored. |
| Rolv-Arild/replicar | v2 README and replay reconstruction interfaces | Strong future input for replay reset banks and inferred controls with provenance. It needs an explicit adapter and validation; it is not automatically plugged into this PPO loop. |
| Rolv-Arild/Pearl | README and next-goal-prediction/player-value code organization | Useful for later evaluation/reward research; player value is not a ready-made controller or proven online reward. |
| VirxEC/rlgymppo_rs | Trainer, transfer-learning example, migration guide and workspace model interfaces | Current Rust/Burn/RocketSim-v3 interfaces differ from the pinned Python stack. The transfer example explicitly leaves its critic untrained and rewards as metrics; this release runs actual PPO with a trained critic. No silent backend substitution. |
| VirxEC/rlgym_rs | RocketSim-v3 environment interfaces | Record as a native-backend candidate; retain the existing simulator until trace/serialization parity is demonstrated. |
| VirxEC/rlviser-py | socket framing and fixed ports | Keep the verified 0.6.14 sender and opt-in native UDP checks. Do not use the incompatible legacy sender with the camera viewer. |
| ZealanL/GigaLearnCPP-Leak | Learner / PPO config and policy-version handling | Useful architecture reference, but archived and no explicit root license was identified. Do not vendor it as the new trainer or claim its throughput. |
| ZealanL/RLGymPPO_CPP | Learner and PPO structure, README | Native high-throughput option for later parity testing. Preserve the pretrained policy first; throughput alone is not evidence of learning. |
| ZealanL/PolicyPlasticity | README and synthetic-task diagnostic | Plasticity score is not match strength. Keep it as a diagnostic experiment, not an optimization target or reason to reset strong weights. |
| ZealanL/RocketSim and RLGymSim_CPP | Simulation interfaces / build layout | Pin the installed RocketSim 2.2.1 behavior for this branch. Do not mix it with the newer Rust engine's types or timestep conventions. |
| SubparN0va/GGLBot | Native v5 launcher, architecture/config requirements | Export both native-compatible SHARED_HEAD.lt and POLICY.lt. Their builder, parser and timing must still match the runtime. |
| SubparN0va/ByteBotpack and botpack fork | Byte family models, ByteObs/ByteAction, v5 configs and botpack-fork organization | Treat bot availability separately from trainable/adapted weights. Byte/Kilobyte/Megabyte are promising further opponents but need their own validated observation/action adapter; they are not silently treated as Chronos. A bot's name in a pack does not prove a headless PPO adapter exists. |
| RLBot/python-interface, core and flatbuffers-schema | Hivemind, ControllerState, frame counter, boost timer and jump fields | Use a distinct v5 agent ID, the v2 compatibility GameState directly, correct countdown/reset handling and delayed neural control. |
| RLBot/botpack | Public catalog and previously pinned teachers | Reuse the four verified model adapters; do not invent a Pulsar identity. |

## Implemented versus deferred

Implemented: real Chronos actor initialization, a new separate critic, critic-only warmup, PPO rewards on learner actions, frozen Chronos KL anchor, masked 90-action sampling, delayed execution, multi-bot opponents, snapshot self-play, pause/resume, W&B, initial-vs-current screening, RLViser camera, metrics-only reports, and native-component / v5 export.

Also fixed: an orange reset mutated shared kickoff spawn arrays. Tests now require unchanged templates, repeatable seeded resets, and matched initial observations before calling a comparison paired. Historical kickoff comparisons from the affected code should not be used to rank policies.

Deferred: native multi-game rollout integration, Rust/Burn checkpoint conversion, automatic human replay reconstruction, 2v2/3v3, and a proven match-strength gain over original Chronos. Those require separate interface changes or evidence. The original Chronos repository has no explicit root weight license; this source ZIP does not redistribute its weights or grant new rights over them.

## Next research gates

1. Run the new student from original Chronos weights and verify the initial watch behaves competently.
2. Compare a short fine-tuning run against its exact initialization on paired fixed starts, then on a fresh seed set and full offline games.
3. Review score, conceded goals, contacts, reward contributions, anchor KL and opponent coverage before extending the run.
4. Port to a native multi-game backend only after identical observation/mask/action-delay traces and component weight loads pass; report learner decisions/sec and end-to-end learning separately from raw physics SPS.
