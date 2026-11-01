# Freestyle implementation research

Reviewed on 2026-10-14. This document separates upstream observations from
implementation recommendations. These sources do not establish that a newly
initialized bot will learn TAS-like play on a laptop within a particular time.

## Sources and revisions

| Source | Revision inspected | Useful scope |
| --- | --- | --- |
| [SubparN0va/GGLBot](https://github.com/SubparN0va/GGLBot) | `d5d21daa7653f842699b590d6bf85597c617e4d8` | RLBot v5 deployment of GigaLearn policies |
| [PiggyVevo/GigalearnGuide](https://github.com/PiggyVevo/GigalearnGuide) | `cc5152b2b11e09d39bcd2b2d3cf27d555db335c2` | Windows setup, example training and rendering |
| [ZealanL/GigaLearnCPP-Leak](https://github.com/ZealanL/GigaLearnCPP-Leak) | `86e11c3881a21225a43c36b14af40f0b3c87e7dd` | C++ PPO, RLGymCPP, bundled RocketSim |
| [ZealanL/RLGym-PPO-Guide](https://github.com/ZealanL/RLGym-PPO-Guide) | `cef4469986d8147cc9071af2b561917790ac00ae` | Reward design and learner interpretation |

The last source's requested pages were all read:
[making a good bot](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/making_a_good_bot.md),
[learner settings](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/learner_settings.md),
[graphs](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/graphs.md), and
[rewards](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/rewards.md).
The bot/reward/graph pages explicitly describe parts of their advice as work in
progress. They are experience-based guidance, not controlled benchmarks.

## What the sources establish

GGLBot is an inference/export application, not a trainer. Its README describes
an RLBot v5 executable taking the same observation builder, action parser,
architecture and `.lt` models as the trained bot. Changing observations or
action ordering requires matching deployment code. It does not make RLBot v4
able to load an arbitrary new architecture by itself.

GigaLearn is a PPO trainer using RocketSim CPU physics and LibTorch inference
and optimization. Selecting CUDA does not move the arena physics to the GPU.
The native setup in this project already pins the inspected upstream revision;
a new checkout of the same revision cannot by itself solve reward or rollout
problems. Performance comparisons must use the same physics tick rate, action
rate, car count, observations and network size. Physics ticks, individual-car
decisions and learned transitions are different units.

Zealan's guidance starts with ball touches, movement toward the ball and
retaining jumping. It warns that a fresh policy can abandon jumping because
ground approaches are easier. Once touches are frequent, it recommends
reducing their weight and introducing goalward ball movement. It warns against
oversized early goal rewards and against farmable repeated-touch rewards.
The guide's suggestions of roughly `2e-4`, then `1e-4`, then `8e-5` learning
rates are examples of progression, not required values.

For aerial touches, the guide recommends combining height with time airborne;
height alone encourages simple high wall touches. It recommends custom rewards
for mechanics which do not emerge naturally. It also cautions that early team
reward sharing and zero-sum specialist rewards add noise. Freestyle practice
can begin without opponents or team sharing and introduce defenders later.

The guides disagree in places. PiggyVevo's inspected `ExampleMain.cpp` uses a
large early goal reward, one epoch and normalized entropy `0.035`, whereas
Zealan's reward guidance advises gentler goals and two or three epochs. The
example also contains a stray standalone period in its environment function.
It should be treated as an illustrative configuration, not copied as a known
working source file. Its comments about powerful desktop GPUs do not determine
settings for a GTX 1650 laptop.

## Actual reset and contact APIs in the pinned simulator

[`RLGC::Player`](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/RLGymCPP/src/RLGymCPP/Gamestates/Player.h)
inherits RocketSim `CarState`. The pinned
[`Car.h`](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/RLGymCPP/RocketSim/src/Sim/Car/Car.h)
exposes `wheelsWithContact[4]`, `worldContact`, `ballHitInfo`, `hasJumped`,
`hasDoubleJumped`, `hasFlipped`, `isFlipping`, `airTime` and
`airTimeSinceJump`. `isOnGround` means at least three contacting wheels, which
can include contact with the ball; it is not an arena-floor classification.

In the pinned
[`Car.cpp`](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/RLGymCPP/RocketSim/src/Sim/Car/Car.cpp):

- `HasFlipOrJump()` checks ground contact or available jump resources and timer.
- `HasFlipReset()` means airborne, jump/flip available and `hasJumped == false`.
- `GotFlipReset()` means airborne and `hasJumped == false`, even if already used.

Neither reset helper alone proves that the resource was acquired from the
ball. Driving off a surface without jumping or setting an airborne car with
default flags can satisfy the helpers. State setters must initialize resources
deliberately. A ball-reset reward needs a physics-tick event with wheel contact,
ball contact, location/orientation checks and resource acquisition. It must
exclude world-contact recharge, latch until the resource is consumed, and avoid
paying again for continued contact. A repeated-reset reward needs separate
acquisition and consumption events for each reset.

The pinned `BallState` has no public per-tick world-contact event flag. Backboard
and wall rebound detection based on boundary position plus a velocity-direction
change is an inferred event and should be labelled accordingly. A proximity
test alone does not establish a pinch, double tap or psycho. Attribution also
needs recent learner contact, the required rebound sequence, bounded timing,
and the appropriate scoring direction.

GGLBot's inspected `ToPlayer` reconstructs jump/dodge flags and approximate air
timers from RLBot v5 packets. It does not populate four wheel contacts, simulator
contact normals or `ballHitInfo`. Privileged fields can improve rewards and a
training critic; including them in the actor requires a matching live estimator
or a documented availability mask. Otherwise training and live play receive
different information.

## PPO implementation differences that affect settings

Upstream
[`PPOLearner.cpp`](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/src/private/GigaLearnCPP/PPO/PPOLearner.cpp)
uses a clipped categorical PPO objective with default clip range `0.2`, gradient
norm clipping at `0.5`, and entropy divided by a log action-count scale. Its
minibatches accumulate gradients into a batch optimizer step. CPU mode runs a
whole batch rather than the configured CUDA minibatches. Its stock reported KL
is measured during minibatch forward passes, before the corresponding optimizer
step; project patches add an after-step measure. Stock reporting is not a hard
KL acceptance gate.

Project `AttentionPPO.h` is a separate PPO implementation for the old attention
actor. It uses clip range `0.15`, raw entropy coefficient `0.003`, a frozen-teacher
KL anchor, and epoch rollback/backtracking on full-rollout KL. It must not be
described as numerically identical to GigaLearn PPO. A random fresh actor should
not be anchored to a frozen random actor. The old continuation learning rate
and teacher weight are unsuitable scratch defaults.

The Python guide suggests keeping previous experience batches. Inspected native
GigaLearn replaces the experience tensors each iteration; it does not implement
that setting. For the new trainer, current-policy rollouts are the simplest
PPO baseline. Old replay actions cannot be passed through the PPO loss as if
they were newly sampled on-policy actions.

## Recommended design and initial laptop budget

These are engineering starting points, not established optimal values:

- Use the existing pinned C++ RocketSim dependencies and a separate scratch
  trainer/run directory. Initialize every policy parameter from the new random
  seed; record initial hashes and schema. Keep old champions as optional later
  opponents, not hidden initialization or mandatory teachers.
- Start with roughly `512,512,256` hidden policy/critic capacity, or a comparably
  sized entity encoder. Preserve normalized relative ball/car physics, angular
  velocity, orientation, boost, last action, jump availability, surface geometry
  and task context. More neurons cannot compensate for incorrectly detected
  events or absent observations.
- Start with 16–32 worlds, 16k–32k learned transitions per iteration, minibatches
  1024–2048, two epochs, LR about `2e-4`, clip `0.2`, GAE lambda `0.95`, max
  gradient norm `0.5`, and raw entropy around `0.01`. If using upstream normalized
  entropy, account for its different scale. Keep settings adjustable. Reduce
  minibatch/network/world count if VRAM or RAM is exceeded.
- Use normal soccar physics. A four-tick decision interval gives 30 decisions/s
  and finer jump timing than the old eight-tick actor, at additional inference
  cost. Do not change tick interval on resume. Keep training and export action
  hold/delay identical; reward and observation event tracking can run at every
  120 Hz physics tick.
- Express discounting in game seconds: `gamma = 0.5 ** (tick_skip / (120 *
  half_life_seconds))`. At four ticks, half-lives of 5s and 10s imply approximately
  `0.995389` and `0.997692`; reusing `.995` at a doubled action rate halves its
  effective horizon. Start shorter for contact drills and retain a longer
  horizon for timed mechanic-to-goal sequences.
- Scale continuous rewards by simulated elapsed time. Cap generic approach,
  orientation and airtime rewards so survival/hovering cannot outweigh genuine
  skill events. Do not pay proximity as if it were a touch.

## Curriculum and objective checks

Use staged scenarios which preserve prerequisites but initially give the learner
a reachable later subtask. Progress from approach/jump touches to aerial
interception, controlled carries, wall climb/pop, reset acquisition/use,
multiple resets, pinch/double-tap and psycho/walldash practice. Blend in earlier
stages instead of deleting them. Randomize position, orientation, velocity and
boost gradually; successful fixed-start tricks do not prove generalization.

Pay each chain milestone once and bound intermediate reward. A score can add a
larger bonus for a verified chain, but success must still be measured with
independent event counters rather than reward sum. Reset stacking requires
consumption, new acquisition and further useful ball contact. Limit reset-chain
duration and maximum payout to avoid indefinite reward farming. Wall dashes
need wall contact, jump/flip transition and measurable useful motion; counting
button presses alone teaches button spam. Pinches need a large ball impulse near
the appropriate surface; ordinary wall contact is insufficient. Treat such
geometry-based classifications as proxies until validated visually.

Promote stages/checkpoints using a reserved scenario bank with fresh held-out
seeds. Record successes/opportunities and randomized-start success, and compare
to the parent on the same conditions. Do not certify mastery from training reward
or a handful of successful starts. A freestyle score and competitive match
win rate are separate outcomes and should have separate report columns.

## Monitoring and validation checklist

W&B should log the active stage, difficulty, individual reward components,
event/opportunity counts, evaluation success, episode length, touches, airborne
control duration, reset acquisition/use/chain lengths, scoring after mechanics,
policy entropy, clip fraction, rollout KL, value loss/explained variance,
gradient norms, LR, throughput units and VRAM. Log per-second and per-episode
values so shorter successful episodes are not mistaken for deterioration.

Use the locally configured W&B credential when available. If missing, request
it through the local CLI's hidden-input login; do not put it in Studio presets,
command-line arguments, reports, checkpoints or Git. Return the run URL, and
make pause/resume reuse the saved run ID. Local metrics should remain available
if networking or authentication fails.

Before a long run, check nonzero finite gradients and changed actor weights,
each scripted event detector's false positives, seeded-air reset behavior,
per-world GAE boundaries and timeout bootstrapping, fresh vs resumed action
parity, checkpoint completeness, and missing-observation handling in live
export. Report successes as observed evidence, not an assurance of learning
multi-reset psychos within a fixed step budget.
