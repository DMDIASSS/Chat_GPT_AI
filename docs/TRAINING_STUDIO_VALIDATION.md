# Training Studio validation

These checks use the original SHA-verified Nexto attention actor as an integration
fixture. The user's original mechanics checkpoints 1–400, strong update180/278,
team updates and local native attention197 are on their Windows PC. The checks
below establish execution and preservation, not improved playing strength.

## Implemented workflow

The desktop Studio provides staged model inventory/selection, native attention
training, automatic champion branches, safe pause/resume, saved reports, model
browsing and learned/scripted RLBot exports. It exposes supported native,
selector and campaign parameters through forms and JSON. Balanced-team and
all-nine-roster presets keep training and campaign evaluation formats aligned.
Replay preparation and the previous MLP input-audit tool are available separately;
the attention learner does not currently apply human replay gradients.

The native learner uses the original 44-tensor, 444032-parameter attention actor,
C++ RocketSim collection and LibTorch PPO. Each arena contributes only the
selected learner's experience. Frozen teammates and rivals retain their own
inference/action clocks and scripted kickoff. Learner seats and colors rotate
independently of roster choice. Normal matches are retained alongside targeted
practice; each task uses its corresponding critic head.

Recent self-play actors are independently loaded from completed checkpoints.
The frozen source teacher remains unchanged. The pool retains three recent
snapshots and versions still used in active episodes, plus pinned historical
opponents. Resume restores optimizer/RNG/task progression and the snapshot pool;
physical arenas restart from saved next episode seeds.

## Checks performed

The targeted release suite passed **161 tests with no skips**. Windows Python3.11
syntax was checked. The source-only ZIP was extracted over a clean tracked base;
its actual Tk interface, boost training/resume, cached selection and both RLBot
kickoff exports ran successfully using the already validated CPU build.

- Native Release builds produced the training, observation parity and PPO parity
  executables against the pinned GigaLearn/RLGymCPP source. No legacy MLP build
  or protected checkpoint was replaced.
- Observation parity covered all nine team rosters and both colors: 108 injected
  physical states, 432 player views and policy action agreement.
- PPO checks changed all 44 actor tensors, kept the teacher unchanged, verified
  exact CPU optimizer/RNG restoration and exercised rollback/device relocation.
- Actual boost training across 1v1/2v2/3v3 performed two PPO updates and resumed
  for a third. Match/boost rows reached critic heads0/9; an inactive head stayed
  unchanged. Completed snapshots survived unchanged and a new one was added.
- Actual wall practice retained a normal arena and trained its separate critic
  head. Task success/deadline endings are terminals without timeout bootstrap.
  Randomized starts, wall/nose/reset events, deadlines and anti-farming rules were
  tested separately, including real wall contact and four-wheel ball contact.
- Defense/recovery/boost/bump/evasion fixtures checked 108 start combinations,
  actual pad pickup, attribution, boost sharing and bounded event payments.
- Staged selection completed all four fixture stages with144 cached games.
  Budget-stop/resume reused records; exact cutoff ties remained eligible; later
  stages used candidate-policy squads. Selection-to-training preserved an
  immutable selection snapshot and original sources.
- Actual campaign checks ran normal-match and boost branches, parent comparisons,
  retained parents, and saved all checkpoints. A defense run safely paused after
  one update, resumed the two remaining updates and reused completed games.
- Desktop Tk startup and a real background status job passed using a local dummy
  X display. Scrollable controls were checked at1024x768. Background detach,
  reconnect, one-job guard, profile precedence and export checks passed.
- CUDA-valued TorchScript graph constants were tested on CPU: shared loading
  reconstructs the verified CPU graph with identical saved weights and actions.

## Practical limits

A ranking based on short games can be inconclusive. The selector retains ties
and labels exploratory results. The campaign includes the parent, checks the
newest model for regression, selects historical branch candidates, and requires
fresh confirmation plus per-mode guards before changing its private champion.
Bootstrap coverage and finite samples cannot guarantee the globally best model.
The protected playing model is never automatically overwritten.

CPU cloud checks do not execute Windows batch scripts, Visual Studio, live
Rocket League/RLBot or CUDA kernels. After extracting, rebuild through the Studio
and run parity/smoke on the intended local device. Code/binary/runtime changes
require a new run from a selected actor; older full runs remain preserved.
Training and evaluation durations are bounded but may finish their current
chunk/group after a campaign time limit. GPU throughput and improvements must
be measured on the user's hardware and checkpoints.
