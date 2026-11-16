# Stationary targets, moving targets, then normal match checks

Extract the update into `E:\Downloads` so it merges with
`Chat_GPT_AI\duelforge`. Keep the current native binary, environment, and runs.
No reinstall or native rebuild is needed. Close other trainers before starting.

## Buttons

- **56_START_STATIONARY_AIR.bat**: fork the tested `jump01` candidate into a new
  `runs\held01` experiment. Train **500,000 additional learner transitions**
  per invocation (rounded up to a complete PPO rollout), then run skill probes,
  200 normal 100-second matches against the exact frozen source, save a report,
  and pause. The absolute transition counter includes the inherited training.
  A 90-minute backstop also saves and pauses. If paused early, 56 starts another
  bounded block from the saved checkpoint. No original is replaced.
- **57_WATCH_STATIONARY_AIR.bat**: watch actual neural controls on suspended-ball
  drills. Both colors use the new actor. The ball remains stationary until real
  contact, and the drill then resets. These are training scenes, not regulation
  matches. Current curriculum height/distance is used.
- **58_WATCH_STATIONARY_MODEL_MATCH.bat**: normal physics, blue = new candidate,
  orange = its exact frozen `jump01` source. No suspended targets.
- **59_REPORT_STATIONARY_AIR.bat**: creates `DuelForge_held01_report_*.zip` beside
  the launchers. Send this ZIP after the first 500k block.
- **60_PAUSE_STATIONARY_AIR.bat**: save at the next complete update. Ctrl+C in
  the trainer also requests a save. Evaluation completes its current panel.
- **61_EXPORT_STATIONARY_AIR.bat**: existing RLBot v5 export (TorchScript `.lt`
  + `.toml` wrapper and `.pt`). The export contains a neural actor; it does not
  freeze the ball in Rocket League. This does not promote the candidate.
- **62_EVALUATE_STATIONARY_AIR.bat**: another 200 normal matches against the
  frozen source. Repeating the same seeds is not new independent evidence.

The W&B uploader stays separate from training. It uploads local metrics and
can remain open for resumes; Ctrl+C in that window closes it. It never trains.
Existing uploaders for other experiments do not upload `held01`.

## Task and rewards

Initially arenas are allocated 35% stationary targets, 15% released moving
targets, and 50% ordinary matches (rounded by arena count). Roles stay fixed
within the session so four-second drills cannot be diluted by long matches. Cars have normal jump/boost/flip state and full native
action masks. A suspended ball uses the installed RocketSim engine's exact-zero
linear/angular velocity sleep behavior. There is **one state injection at the
start of a drill**, never a per-frame car reset. A startup check verifies this
behavior in the installed binary before training. Moving targets start with
nonzero velocity and use normal gravity immediately.

Each drill lasts at most four seconds and ends at the first elevated physical
contact: the ball must be at least 220 units high and the contacting car's center
above 65. The contacting car gets +1 once. Approach displacement adds at most
0.02 per decision; jumping in place or staying airborne receives no bonus.
Goal reward +1 and concede penalty -1 remain. Normal matches retain the existing
trajectory possession/first-contact objective.

Entropy coefficient is **0.020 on drill learner rows**, versus **0.003 on normal
match rows**. It is stored with each rollout row, so resets do not change the
coefficient of previously collected examples. Frozen opponent rows never enter
PPO losses. More entropy encourages exploration; it cannot guarantee jumping.

Difficulty increases by at most one level between completed 500k blocks. At
least 128 current-level stationary trials must have completed. The frozen greedy
actor must reach >=75% on current-level stationary probes and >=50% on moving
probes, retain easy contact within 10 percentage points of its source on the same
cases, and avoid a clear match regression. Exploration successes alone never
advance it. Twenty
percent of drill resets retain the easiest level. Heights/distances:

| Level | Ball height | Car horizontal distance |
| --- | --- | --- |
| 0 | 240–340 | 180–420 |
| 1 | 300–450 | 250–650 |
| 2 | 400–650 | 350–900 |

After success at level 2 the distribution becomes 15% stationary, 35% moving,
50% normal. Level and rolling success window resume from the checkpoint.
Simulator episodes restart on resume, as in the existing trainer.

## What the report establishes

Before/after probes measure greedy jump use and actual elevated contacts in
balanced colors, with an inactive distant opponent. Stationary and moving
targets are checked separately; the source is checked on the same final cases.
The stationary physics check, exact source/candidate hashes, reward config,
curriculum state, local metrics, match results, and source hashes are included.
Normal matches use the bare native simulator, never the drill wrapper.

A normal-match confidence interval entirely below 50% pauses further unchanged
training. Otherwise 56 can add another bounded block. No automatic promotion or
claim of stronger overall play is made from a drill score. Source `jump01`,
confirmed trajectory weights, and failed `air01` experiments are preserved.

The published validation uses local smoke-test actors, not your latest Windows
weights. Your first report is needed to measure whether this transfers to the
bot you are watching. The previous narrow jump bootstrap did not establish
reliable aerial behavior in ordinary matches; this update addresses that gap.
