# v1.7: unattended Chronos, fusion experiment and both export formats

Your 63,490-decision report scored 94 first-goal wins / 22 losses / 34 timeouts, versus original Chronos's 101 / 20 / 29 on 150 trials. The difference is inconclusive. A good watch session is consistent with this: the learner is capable, while improvement over its initialization is not established. The W&B web page could not be opened here; the uploaded report supplied the optimizer and episode metrics.

## Update and continue your good Chronos run

1. Pause with **36**; wait for the training console to exit. Close viewers with Ctrl+C.
2. Merge the source ZIP into your existing chat_gpt_ai/novaforge. Keep .venv, assets and runs. Run **1_CHECK.bat**.
3. Run **35**. The known v1.6 configuration is upgraded automatically. Previous config and full checkpoint are preserved under runs/chronos01/upgrades/pre_v1_7_0. Actor weights and step-0 initialization are preserved. The critic and optimizer momentum are reset for the changed return objective; 16 critic-only rollout updates precede actor updates. W&B reuses the run's existing ID/login.
4. Leave 35 running. It checkpoints regularly and performs automatic timed W/D/L comparisons every **131,072 learner decisions**, checking on segment boundaries. An existing run receives a comparison before further updates on its first upgraded launch. Evaluation time does not count as training decisions; CPU throughput will pause during these checks.
5. **36** pauses. **37** shows status and any halt reason. **38 still watches the latest learner**, preserving the previous watch behavior. **51** watches the protected champion; **42** watches original Chronos.
6. **40** exports the protected champion in both formats. **41** exports a selected-metrics report. **50** manually compares the latest learner and original Chronos with timed games. **39** retains the older first-goal screen.

A champion begins as unchanged Chronos. A candidate must improve in a rotating development match set and a fresh confirmation set before promotion. Checkpoint pruning never removes the current champion. Latest training and champion are deliberately separate: a good-looking latest policy can be exported explicitly with the CLI below if desired.

## Rewards and safeguards

For an eight-tick decision the reward is:

`10 * (score - concede) + gamma * Phi(next) - Phi(current)`

`Phi = 0.35 * team_relative_ball_y / 5120 - 0.1 * min(car_ball_distance, 12000) / 6000`

Phi(next) is zero on a goal. At a time limit it stays nonzero so SB3 bootstraps the final observation. Timeouts occur only on full eight-tick boundaries. There is no flat touch, aerial or survival bonus. Discounted potential shaping telescopes: loops do not generate an extra discounted return independent of the endpoint. Tests cover goals in either physics half, terminal accounting, time-limit handling and loop accounting. This is a new objective; original teacher training rewards are not public.

Gamma is now 0.999 per eight-tick decision, extending credit over tens of seconds. Defaults use 50% ordinary kickoffs and retain mechanics starts. Actor updates use 5e-6, clipping 0.05, a frozen Chronos KL anchor and critic warmup. These are tested conservative starting settings, not proof of optimal hyperparameters.

Automatic comparisons use four frozen opponents, both colors and actual multi-goal 60-second simulator games. Level scores are draws, not timeouts. Goal pauses and overtime are omitted. Team colors sharing a seed are treated as one statistical block. Promotion requires a positive margin and uncertainty check, fresh-seed confirmation, and a per-opponent degradation limit. These reduce selection risk; repeated evaluations are not a formal unlimited-time guarantee.

Training **stops** after two clear negative comparison sets or one large clear drop. The actor is restored from the retained champion before saving; the champion remains exportable. Three consecutive updates exceeding the mean anchor-KL limit also stop training. Nonfinite losses/gradients restore pre-update parameters before an error checkpoint can be saved. Check 37/status.json for the reason. A reviewed halt can be cleared explicitly with `chronos-train --run chronos01 --resume --forever --wandb online --clear-halt`; do not automatically restart an unexplained halt.

No reward can promise monotonically improving Rocket League play on an unattended laptop. This release makes deterioration visible and keeps a protected export instead of silently treating the latest weights as best.

## Combining Chronos, Ripple and Galactus

Their raw weights cannot be averaged: the networks have different dimensions, feature builders and action interfaces. The included experiment combines **probabilities after action mapping**, then distills into the original Chronos architecture. It is informed by [policy distillation](https://arxiv.org/abs/1511.06295); [model soups](https://arxiv.org/abs/2203.05482) concern compatible fine-tuned networks, not these heterogeneous teachers.

Chronos supplies 50% of the target distribution, Galactus and Ripple 25% each. Teacher tensors stay frozen. Ripple's 276 actions are projected to Chronos's 90 actions; its longer queue is approximated with held controls. These approximations can lose skills. A small distillation rate and frozen Chronos KL anchor limit changes. After the bounded distillation phase, ordinary PPO trains the single student against the four frozen opponents and snapshot self-play. Deployment uses one network.

**Pilot evidence:** eight paired 30-second simulator games, two colors across four opponents, on development seeds. Original Chronos: **6 W / 2 D / 0 L**. Raw probability ensemble: **4 / 1 / 3**. Single student after only 1,024 distillation decisions: **4 / 3 / 1**. This does not establish a better combination. No experimental weights replace your existing run or are shipped in the source ZIP.

To try the separate **fusion01** run:

- **43:** start/resume bounded 32,768-decision three-teacher distillation, then guarded PPO continuously.
- **44:** pause; **45:** watch its protected champion; **46:** compare latest student vs original Chronos with W/D/L.
- **47:** export protected champion in both formats; **48:** report. An unpromoted fusion run exports original Chronos unless `--latest` is chosen explicitly.
- **49:** benchmark the raw three-network probability ensemble against original Chronos. It does not change training weights.

Only run one training/viewing benchmark workflow at a time on this laptop. Distillation is resumable at saved batches; in-flight arena/RNG state and an unfinished batch are not restored exactly. Its setup phase logs to the console/local files; the subsequent PPO phase uses W&B.

## .pt + .cfg and .lt + .toml

Launcher 40 (chronos01) or 47 (fusion01) creates one export folder and ZIP containing:

- **actor.pt + bot.cfg + bot_v4.py:** RLBot v4. Import bot.cfg using a separate Python 3.11 x64 v4 environment and install requirements-v4.txt there. Never replace the training environment's v5 SDK with v4. The folder is self-contained for v4.
- **actor.lt + bot.bot.toml + bot.py:** RLBot v5. Keep it under novaforge/exports and import bot.bot.toml.
- **SHARED_HEAD.lt / POLICY.lt:** native Chronos-compatible network components; native observation/parser/timing must still match.
- **actor_weights.pt:** a plain state_dict for custom Python code, plus selected training_config.json. Full PPO/optimizer resume still uses the checkpoint ZIP under runs.

actor.pt and actor.lt are identical TorchScript network bytes with matching metadata. A CFG/TOML file configures its matching runtime; renaming an arbitrary model is not conversion. The v4 SDK exposes less jump state and estimates flip timing; v5 is preferred for precise transfer. Both still need live full-game verification.

Explicit latest export/watch commands:

```bat
.venv\Scripts\python.exe run.py chronos-export --run chronos01 --latest
.venv\Scripts\python.exe run.py chronos-export --run fusion01 --latest
.venv\Scripts\python.exe run.py chronos-watch --run fusion01 --latest
```

## Separate random-router project

[TriadBot](SECOND_PROJECT.md) keeps all three networks loaded and chooses one expert per decision, boosting long-waiting experts and penalizing repeats. It is a separate runtime experiment, with a portable personal v5 export. It does not merge or train the three networks.
