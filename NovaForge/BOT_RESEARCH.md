# What the public bots make available

Sources were inspected through the user's [RLBot botpack](https://github.com/RLBot/botpack/tree/master/Botpack). This is an interoperability review, not a verified ranking of playing strength. A deployment model usually does not include training data, reward code or optimizer state.

| Bot | Public material inspected | Use in NovaForge v1 |
| --- | --- | --- |
| Ripple v1.1 | Python observation/action code, ONNX policies, runtime, notices | Real simulator trainer and demonstration collector. Fixed deterministic RL policy, original six-slot queue, four-tick decisions. No adaptive runtime bandit/BCM blending. |
| Nexto | Public neural policy and observation builder | Real eight-tick neural opponent/teacher. Stock scripted kickoff is not included, so label comparisons `Nexto neural` rather than exact stock Nexto. |
| Chronos | C++ GigaLearn inference project, padded observations, action code, `.lt` weights | Source study and later offline RLBot opponent. A correct headless port remains future work. |
| GalactusV2 | C++ GigaLearn inference project, 258-feature builder, 90 actions, `.lt` weights | Source study and later offline RLBot opponent. Its prediction samples, timers and action delay need their own parity tests. |
| Pulsar | A public C++ training research repository was found | Algorithm study only. It is not listed in the inspected botpack snapshot; this repository's identity as the specific strong bot the user means, and a compatible deployment checkpoint, were not established. |

## Ripple: useful material available now

[Ripple's runtime](https://github.com/Rolv-Arild/Ripple-RLBot/tree/7ca4273a891ab1d04d001b48cb86f1bc8914aa85) publishes both observation construction and the action-delay mechanism. Its exported network uses cross-attention over game entities, a simulated ball forecast and action embeddings. The 1.1 policy is relatively small, which makes it a practical CPU trainer for this laptop.

NovaForge downloads the exact observation/action code and policy. The adapter translates RLGym states into the expected legacy representation, corrects boost units, puts the controlled car first, preserves the delayed queue, and runs the ONNX graph on one CPU thread. The graph handles action-index reversal after side mirroring. Tests exercise both sides, non-kickoff states and the six-decision delay. Live parity and stock bandit playing strength have not been established.

## Chronos and Galactus: interfaces matter

[Chronos](https://github.com/KingJake3113/Chronos/tree/4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa) uses C++ inference components from the GigaLearn ecosystem. The supplied repository is a deployment/build path; batched inference of teammates does not itself provide a training algorithm or team coordination. Its observation padding and action masks must be matched when reusing weights.

[GalactusV2's public README](https://github.com/SoldierDoge/GalactusV2/tree/217324c2fc516048effe0407595fa61c2ebc6863) specifies 258 observations, 90 discrete actions, tick skip eight and delay seven. The feature builder includes boost timers and ball-prediction samples. It supplies inference weights rather than resumable optimizer/training state. Loading these files into the new 100-feature/276-action student would be incompatible.

The immediate way to test either bot is to export NovaForge into RLBot v5 and play offline matches. The next headless adapter should begin with recorded-state parity against the original C++ runtime, including ball prediction, queue phase, normalization and action masks.

## Pulsar: a research direction, not a bundled trainer

The [Pulsar source found in this review](https://github.com/lucamignatti/pulsar/tree/3e6f127c0dbe4c539962d67d5803301188128d6c) describes sparse-goal PPO combined with a goal-conditioned contrastive critic and an expanding reachability curriculum. Those are substantial training-system changes. The identity/checkpoint ambiguity above prevents treating this repository as a verified instance of the user's named opponent.

NovaForge currently implements outcome-based adjustment of seven practical reset scenarios and a `sparse` reward option for controlled experiments. It does not implement the contrastive critic or Pulsar's spatial grid. Those ideas should be tested as separate runs against the shaped-PPO baseline, with replayed held-out evaluation seeds.

## Why start with the small Python trainer

The existing project already experiments with GigaLearn/C++. This new folder provides a short inspectable loop with actual teacher interoperability and reproducible reports. That establishes a reference behavior before a native-performance port. A later C++ rollout collector should match the reference state/action/reward traces before throughput comparisons.

Supporting documentation:

- [RLGym v2 quick start](https://rlgym.org/Getting%20Started/quickstart/)
- [RLGym tools replay support](https://github.com/RLGym/rlgym-tools)
- [Stable-Baselines3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html)
- [RLBot](https://rlbot.org/)
