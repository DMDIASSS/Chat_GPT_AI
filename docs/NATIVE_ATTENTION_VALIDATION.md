# What the native attention milestone verifies

The implementation reuses pinned GigaLearn's RLGymCPP/RocketSim simulation and its thread pool, with a LibTorch attention-policy PPO adapter. Source actor parameters are inherited exactly; its critic and optimizer start fresh. Normal-match observations, 90-action ordering, 8-tick timing, reward formula, teacher anchoring, GAE and PPO objective follow the existing strong attention trainer.

Executed cloud evidence:

- 108 actual simulator-state observation fixtures and 432 player perspectives cover all nine roster configurations, both colors, airborne/flip/demo/cooldown states and previous controls. Observation errors ≤2e-6; original Nexto logits match exactly on the checked views.
- A 190-packet clock comparison covers frozen kickoff interruptions and reentry. Real physics tests cover one old-control tick plus seven new-control ticks, terminal goals, partial timeout and exclusion of frozen experience.
- Fixed-input PPO compares logits, critic, log probabilities, GAE, returns and actual actor/critic updates with Python. Before-update quantities match exactly; post-update logits differ by at most 2.67e-5, critic values by 1.5e-8.
- CPU save/load restores both optimizers and sampling RNG. The next sample, actor/critic update and metrics within C++ are bit-identical. Deliberately rejected PPO restores actor weights and Adam moments, including an originally empty Adam state.
- Integrated native smoke performs real collection and two PPO updates; resume adds updates without rewriting previous checkpoints. A live pause test stopped at a saved update, restored for another update, and preserved all earlier checkpoint bytes and an interrupted partial directory.
- Matched evaluation runs frozen rivals with kickoff scripts and an unscripted learner. Export reproduces native actor weights in the existing Python attention checkpoint format.

The combined launcher, observation, timing, existing versatile trainer and team-format test suite passed all 67 tests. The packaged update was also extracted into a clean checkout and exercised separately; no model weights, replays, exports or native build products are bundled.

Short cloud matched games produced actual goals. Those development screens are not independent proof of stronger play, SSL rank or learned elite mechanics. Cloud integration used the available original Nexto source explicitly. The user's actual update180 remains local and requires the shipped local build, parity and CPU/GPU smoke commands.

The benchmark shares initial actor/critic weights, CPU sampling RNG, kickoff permutations, arena count, action-repeat setting and sample budget. A final CPU run used 8 worlds × 128 decisions × 3 updates, for 3,072 learner decisions:

| Measurement | Native attention | Python attention reference |
| --- | ---: | ---: |
| Collection learner decisions/s | 1,590 | 455 |
| Collection + PPO learner decisions/s | 426, including checkpoint saves | 245, excluding checkpoint saves |

The pinned native simulator is 2.1.1, while installed Python uses 2.2.1. Gradient minibatch ordering and subsequent trajectories can differ. A single CPU result is not a hardware-independent speedup or learning-efficiency claim. No GPU performance was measured in cloud.

Physical arena snapshots are not restored across process resume: completed PPO/checkpoint state is restored, and active games begin from saved next episode seeds. In-process collection continues existing arenas across updates. Replay gradients, new mechanic curricula, whole-squad learning, changed action spaces and automatic promotion are outside this first migration milestone.
