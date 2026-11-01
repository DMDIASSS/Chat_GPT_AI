# Update180 continuation: critic routing and package repair

The reported local verification succeeded with update180 SHA `c84f6f15f35e1b177b86bcfdcd6780519c451e39b2ecfa26965dff4388e6a0a4`, and `actor_weights_identical: true`. The crash occurred during the first PPO update, when an older shared PPO implementation called `critic(x)`. VersatileCritic supplies per-task value heads through `value_for_task(x, tasks)` rather than a task-independent forward.

The prior continuation ZIP omitted `slater_cycle9_native_ppo_v025.py`. Cloud tests used a newer checkout containing the task-aware implementation, so they failed to expose this distribution mismatch. The repair bundles every code file hashed by the trainer's code identity. `package_update180_continuation.py` derives that dependency set from the trainer and refuses missing files. A regression test verifies both coverage and exact shipped bytes.

The configured teacher anchor is now explicitly passed to environments; previously their fixed 0.03 per-state weights took precedence over the launcher's 0.10 argument. A real mixed-task PPO regression checks the requested anchor, correct task heads and finite critic updates without adding an arbitrary forward fallback.

The new default is `update180_continue02`, preserving all failed 01 files and its immutable protocol. The supplied traceback happened before the first updated checkpoint was written. The new run loads the original update180 actor, with a fresh critic/optimizer, rather than attempting to use partially changed in-memory weights from the failed process.

Validation: 42 relevant tests passed. A separate isolated bundle test replaced an older `critic(x)` PPO file with the actual ZIP contents, then executed real RocketSim collection, PPO optimization, checkpoint saving and matched evaluation. Source SHA and initial actor tensor equality remained intact. The smoke's four short paired screens tied 0:0 and retained the baseline; these integration results are not evidence of increased strength. Cloud testing used original Nexto because the user's update180 file is local.

## Linked examples reviewed

- [PiggyVevo/GigalearnGuide ExampleMain.cpp](https://github.com/PiggyVevo/GigalearnGuide/blob/cc5152b2b11e09d39bcd2b2d3cf27d555db335c2/ExampleMain.cpp): uses an MLP shared head, padded observations, default action parser, mixture of kickoff/random starts, goal/touch rewards, separate deterministic render mode and checkpoint folder. Its fresh-model policy LR is 2e-4; this is not evidence that a pretrained attention actor should use that rate. The observation/action contracts must match before loading existing weights.
- [PiggyVevo/ExampleRocketLeagueBot examplebot.py](https://github.com/PiggyVevo/ExampleRocketLeagueBot/blob/a1be24c14bc31f89c84896b5e9f023cba0efb96a/examplebot.py): uses rlgym-ppo with 512-wide MLP policy/critic, goalward-ball rewards, checkpoint resume and RocketSimVis UDP rendering. Its README advises keeping architecture, observations and action parser stable during a run. Its sample folder selection uses lexicographic `max`, which should not be copied as proof of the strongest checkpoint.

The useful practices are stable model/input contracts, compatible checkpoint continuation, deterministic viewing, normal-match starts and outcome-based rewards. Neither inspected example provides a drop-in transfer of update180 attention weights to the current native MLP. External examples were read, not built or substituted into the working environment. Linked videos and Desmos were not viewed; no claims rely on their contents.
