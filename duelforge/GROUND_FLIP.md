# No-boost ground flip-to-contact drill

Extract into `E:\Downloads`, merging `Chat_GPT_AI\duelforge`. No native binary,
runtime, checkpoint, or existing run is replaced. Close other trainers first.

- **63_START_NO_BOOST_FLIP.bat**: fork the tested `jump01` actor into new
  `runs\flip01`; do a brief neural warm-up, then train **500,000 additional learner transitions**, run drill
  checks and 200 ordinary 100-second matches, save a report, then pause. Rerun
  63 for another bounded block. A complete rollout can slightly exceed 500k.
- **64_WATCH_NO_BOOST_FLIP.bat**: blue is the neural learner; orange is parked.
  Ball on the ground, 2240–2260 units away, learner initially stationary with
  zero boost, deadline **2.2 seconds**. The camera stays on blue. Console prints
  whether a real directional flip occurred, contact success, distance, penalty.
- **65_WATCH_FLIP_MODEL_MATCH.bat**: ordinary match; blue = new candidate,
  orange = exact frozen `jump01` source. Both have ordinary boost/game rules.
- **66_REPORT_NO_BOOST_FLIP.bat**: creates `DuelForge_flip01_report_*.zip`
  beside the launchers. Send it after the first block.
- **67_PAUSE_NO_BOOST_FLIP.bat**: request a save at the next completed update.
- **68_EXPORT_NO_BOOST_FLIP.bat**: existing RLBot v5 `.lt` + `.toml` wrapper
  and `.pt` export, with source/export logit and action checks.
- **69_EVALUATE_NO_BOOST_FLIP.bat**: another normal 200-game panel vs source.

The exact source must match its successful jump/bootstrap test report. Failed
`air01`, `held01`, and the confirmed ground bot are not overwritten. Training
has a 90-minute backstop and can be paused with Ctrl+C. Evaluation completes its
panel separately. W&B uses an independent uploader window; Ctrl+C there closes
upload only. Keeping that window open allows later resumes.

## Objective

Half the arenas stay assigned to drills and half to ordinary matches. Drill
roles do not get diluted by short resets. In each drill a randomly colored car
attempts the target alone; the other is parked. Parked rows are excluded from
PPO and learner-step counts. Frozen/history opponents apply to normal matches.

The ball is on the ground, not suspended. The learner starts at rest facing it,
with **zero boost**. Boost actions remain disabled throughout the drill,
including after any accidental boost-pad pickup. Intended diagonal paths avoid
pads. Physical motion and jump/dodge timing use the existing RocketSim engine.
There is no per-frame state injection or jump-state reset.

Only a real directional flip followed by an actual ball collision before the
deadline counts as success. Merely pressing jump, double jumping, flipping in
place, or getting close cannot pass. A speed-gaining flip can finish before
contact: it need not still be rotating at impact.

**Success penalty = 0.** Otherwise, at timeout/invalid contact:

`penalty = -clip(final_center_distance / initial_center_distance, 0.01, 1)`

Closer failures cost less; remaining at the start costs about -1. Distance is
measured at the deadline, not the best position reached earlier. There are no
positive flip/jump/airtime bonuses and no running approach reward in the drill.
Normal matches retain +1 goal / -1 concede and the previous possession objective.

Drill entropy coefficient is 0.020; normal matches retain 0.003. Legal masks
keep jumps and directional dodges available and disable boost. The exported
bot has ordinary match rules, with no drill, parked opponent, boost restriction,
or scripted control sequence.

## Calibration and evidence

Every start checks the installed physics: straight full throttle and a single
jump miss this distance/deadline, while a legal drive–jump–release–forward-dodge
test sequence reaches it without boost. Calibration is empirical, not a proof
over every conceivable control exploit.

To make discovering the two jump presses practical, the first start includes
**300 supervised head updates** from real successful simulator demonstrations.
The first two actor blocks and critic stay frozen during this warm-up; normal
source-policy KL regularization limits disruption. A frozen greedy contact check
selects the candidate, and a separate case panel must reach >=50% success with
normal-policy KL <=0.05 before PPO starts. The source is never overwritten. The accepted warm-up checkpoint is pinned as
`runs\flip01\flip_warmup_accepted.pt`, so later PPO cannot erase that artifact.
Warm-up updates do not count as RL transitions. Interrupted warm-up resumes from
its saved state. Later 63 invocations resume PPO without repeating warm-up.
The demonstration script never supplies live actions in RL, watch, or export;
those actions come from the neural actor. If warm-up fails its gate, the run
pauses and makes a report instead of adding an uninformative long RL run.

Frozen greedy probes use balanced colors and actual physical flip flags/contact
events; the source gets the same cases. They report success, flip use, final
distance, and terminal penalty. Ordinary matches run without the drill wrapper.
A clearly worse normal-match result or greedy drill success below 50% pauses
unchanged continuation. No champion
is replaced automatically. A 500k block is a first measurement, not a guaranteed
learning deadline; judge the drill score and ordinary matches together.
