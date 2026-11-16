# DuelForge 0.3 — early-learning and throughput experiments

## First steps

1. Pause the old trainer, wait for PAUSED_AND_SAVED, then close its Python console so Windows can replace the native module.
2. Extract the ZIP into E:\Downloads, merging its included chat_gpt_ai/duelforge folder with your project. No runs, models, environments or exports are bundled or removed.
3. Run 7_VERIFY.bat. Then run **17_START_LEARNING_V2.bat** (or menu 17).
4. First start profiles 64x256, 128x128 and 256x64 arena/rollout combinations on separate scratch models. All collect 32,768 player transitions per update. A faster combination must beat 64 arenas by at least 10% before selection. This is a short hardware timing check, not proof of equal learning quality. The selected arena/rollout settings are recorded and frozen for the new run. Press Ctrl+C to cancel profiling.
5. Training creates the separate fresh run **duel02** and stops/saves after about 60 minutes. duel01 remains available with its original config. Resume duel02 by running 17 again; it does not repeat tuning or reset its entropy schedule.
6. Pause with Ctrl+C or 2_PAUSE.bat. Run **18_WATCH_LEARNING_V2.bat** to watch open play; blue is duel02, orange is its random initial control. Run **19_REPORT_LEARNING_V2.bat** and send the resulting report ZIP. To use the full menu for this run: `_RUN.bat menu --run duel02` (menu 5 evaluates, 7 exports, 8 opens the inspector).

A first check after 15–30 minutes can reveal errors or emerging behavior. This release does not establish that one hour is enough for useful play. The small-network pilot remained weak. At matched 1,048,576 transitions in one full-size seed, the new setup made 11 contacts versus 8 in a brief open-play check and moved toward the ball more often, but still pressed jump on about 62% of decisions and was farther from the ball on average. That is mixed evidence, not proof of improved play or a fix for flipping. Continued feedback and actual match evaluation are required.

## Changes being tested

The log you supplied contains 3,287,328 learner transitions, median reported update speed 9,282/s, with wide fluctuations. CUDA is active. Its last two discovery panels are entirely draws against the random initial policy. Touch counts have not established improvement. The log alone cannot identify thermal throttling or GPU utilization.

- Higher initial entropy *coefficient*: 0.03, fading linearly to 0.003 over the first 10M learner transitions. Fresh policies were already near maximum legal-action entropy; this coefficient helps preserve exploration, rather than creating useful skills by itself. The schedule resumes from the saved transition count.
- Temporary positive velocity toward the ball (weight .01 per full decision) and an actual-contact bonus (.15 per decision containing contact), both fading to zero by 20M learner transitions. Goals and the old small potential/impulse terms remain. These new terms are experimental: approach reward can encourage unproductive pursuit, and a contact bonus can encourage poor touches. No rewards directly pay for jumping, flipping, facing forward or avoiding reverse.
- Explicit legal entropy limit, entropy coefficient, jump-button, reverse-throttle, forward-drive and bootstrap reward metrics. Maximum entropy is log(number of legal actions), not always log(90). These controls are descriptive metrics, not extra rewards.
- Frozen opponents now evaluate their actor only, skipping the unused critic. A direct test checks identical logits/actions. This reduces inference work but has no measured laptop speedup claim yet.
- The native contact detector reads CarState once per decision instead of every physics tick. A 1,600-decision random-action trace across eight arenas matches the prior binary exactly for all ten checked output arrays. The interleaved CPU collection benchmark showed only about a 1% median gain, with noise. This is not a 10x gain.
- On the CPU server, the three-update full-PPO timing check measured approximately 9.24k, 10.13k and 10.33k learner transitions/s for 64x256, 128x128 and 256x64 respectively. That is about a 12% gain for the last setting in this short test; the laptop must measure its own result.
- A stage profiler measures native collection, neural inference, combined collection, and complete PPO separately. It does not relabel raw physics throughput as learning SPS. Scratch profile weights stay in benchmarks/, separate from your runs.

## Simulator shortcut result

`tools/sim_fidelity_lab.py` compared 60Hz and 120Hz RocketSim on 16 paired ground/air/contact fixtures with identical controls. The 60Hz shortcut failed the fixture tolerances: maximum position error about 53.3 Unreal units and velocity error about 218.7 UU/s within two seconds. Production remains 120Hz with the original seven-tick delay, which also cannot be represented exactly at 60Hz. The lab requires existing optional RocketSim Python bindings and is never used by training.

This is our own vectorized native-collector/PPO framework around RocketSim physics. A new accurate physics engine was not completed. Neither these fixtures nor a screenshot can establish a global 99–99.9% Rocket League fidelity number. The code screenshot provided shows reconstruction/error video logging, not the dynamics model or simulator.

## Terminal reference

Terminal's public write-up reports sparse +1/-1 goals, 70% replay-state resets, entity attention, very large batches and a substantial multi-GPU training budget. Its implementation and weights are explicitly unreleased. See research/TERMINAL_REFERENCE.md for source and implications. This update uses the practical parallelism lesson within the laptop memory budget. It does not claim to reproduce Terminal, add its unavailable replay dataset, or import its model.

README.md documents the original prototype controls; this document describes the added experiment. VALIDATION.json and results/ preserve engineering checks and the actual bounded pilot results. Competitive superiority and local GPU speedup remain unverified.
