# Contact, possession and trajectory experiment

This update creates a separate `runs/contact01` experiment from the current
`runs/potential01/latest.pt`. Pause potential01 before starting it. Its model,
optimizer and results stay intact. No fresh random restart is done: the 57M+
actor is worth preserving. The source actor and its Adam moments transfer;
the critic and its moments reset once when each new objective stage is forked.
Resuming a stage does not reset them again. All inherited counters are retained.

## Install and run

Extract into E:\Downloads and merge `chat_gpt_ai/duelforge` with the existing
folder. This patch uses the working selected Python/CUDA environment and the
existing native module. It downloads no libraries, weights or physics engine.

* 33_START_CONTACT_CURRICULUM.bat: start/resume an additional **5M learner-step**
  session. First skill check after **500k additional steps**. Stage changes are
  automatic. A report ZIP is created after the first skill check and when the
  session stops. Sessions stop on a fixed PPO rollout boundary, so a step target can
  overshoot by at most one rollout. A 90-minute per-block backstop also applies.
* 34_PAUSE_CONTACT_CURRICULUM.bat: request a saved pause; Ctrl+C also saves.
* 35_WATCH_CONTACT_CURRICULUM.bat: current stage against the frozen starting
  potential01 parent, normal kickoff match, both Octane. Actual neural gameplay.
* 36_REPORT_CONTACT_CURRICULUM.bat: create one ZIP with stage reports, source,
  metrics, skill checks and provenance. Send that ZIP for review. No weights or
  credentials are included.
* 37_EVALUATE_CONTACT_CURRICULUM.bat: current stage versus that same parent,
  200 matches of 100 simulated seconds, balanced colors. Discovery evaluation;
  it does not certify promotion or strength against Nexto/Galactus.
* 38_EXPORT_CONTACT_CURRICULUM.bat: existing RLBot v5 .toml/.lt exporter with
  .pt and matching Python wrapper; logits/actions checked. No new v4 .cfg port.
  A live RLBot match must still be tested on your PC.
* 39_PROFILE_CONTACT_CURRICULUM.bat: no-training collection benchmark comparing
  native collection with each stage. It reports collection player decisions/s,
  explicitly not end-to-end learner SPS.

`curriculum.json` records the active stage and **additional steps since fork**.
Console `UPDATE` counts remain total inherited learner transitions, just as in
potential01. Each press of 33 permits another 5M additional steps, preserving
all completed work. Do not run other trainers concurrently on this laptop.

## Recipe and stage gates

1. **Contact:** 80% short randomized ground races; 20% ordinary play retained.
   Both cars use the same learner and symmetric state distributions. Reward
   actual first contact with `exp(-elapsed_seconds / 3)`, once per car/episode,
   plus `0.02 * max(0, velocity_toward_ball/2300)` per full decision to guide
   approach. This is temporary direct shaping, not policy-invariant PBRS. Drills end
   on first contact or after six seconds. No speed, flip or jump-button bonus.
   Goals keep their +1/-1 objective on ordinary episodes. Starting positions
   vary in location, approach angle, boost and initial speed; this is not just
   center kickoff. Contact-stage history opponents are disabled. Jump is
   temporarily masked only inside these contact ground drills, so the first
   task is ground steering/approach. The 20% ordinary play, later stages,
   unopposed skill checks, watch and exports all retain full native controls.
2. **Possession:** estimate earliest reach time to the ball's *current* position.
   Reward `0.04 * dt * tanh(clipped(T_opponent-T_self)/0.6)` and its negative
   for the other car, with the lead capped at 1.5 seconds. This is an occupancy
   reward for sustained estimated advantage, rather than a reward only for
   changes in advantage. A small first physical contact bonus is paid once per
   car/episode. Goals remain +1/-1. 35% short moving ground races, otherwise
   ordinary play. Current self-play plus 25% frozen history opponents.
3. **Trajectory:** same bounded possession and goal objective, using the
   existing native three-second ball forecast and reachability estimate.
   Ordinary native training scenes; no injected contact drills. Prediction is
   used by the reward estimator, not privileged future observations supplied
   to the deployed actor. The forecast is approximate, especially at ramps,
   corners, posts and during future car-ball interactions.

At each 500k-step check, run 64 first-contact trials (32 cases in both colors)
with a stationary opponent parked away. Measure actual contact rate and median
time, counting misses as six seconds. Run the frozen parent on the same cases.
Contact advances after at least 500k stage steps if contact rate >=85%, median
<=2.5s, contact rate is no more than 5 percentage points below the parent and
median is no more than 0.35s slower than the parent. If unmet after 2M stage
steps, pause for diagnosis instead of blindly progressing.

Possession requires at least 1M stage steps, those same contact checks, and
>=55% draw-adjusted first-touch race score against the frozen parent on 64
color-balanced moving-ball trials. It pauses after 4M stage steps if unmet.
A bounded KL controller adjusts Adam's rate between 1e-5 and 3e-4. It raises
the rate by 10% when measured KL is below 0.0015, lowers it by 20% above 0.006,
and retains the existing PPO KL/finite-gradient guards. Actual rates are logged
and saved with Adam. This addresses negligible policy updates observed in
small-model pilots, while leaving healthy KL in the target band alone.

These small discovery gates are noisy; passing is permission to test the next
curriculum stage, not proof that a stronger match-playing bot was produced.
Trajectory continues under the session step budget; normal goal-match panels
and parent comparisons remain the playing-strength checks.

Discovery skill probes use a separate seed range. Training uses its existing
<0x40000000 seed range; skill probes use 0x80000000+, and existing evaluation
uses 0xC0000000+. Seeds and raw probe outcomes are recorded. Simulator episodes
restart at each training block and resumes explicitly record that fact.

The full discounted possession penalty is bounded below one goal in magnitude
at the current gamma, reducing the incentive to concede simply to reset a bad
state. Actual reach-time rewards remain heuristics; they do not prove possession
or remove reward hacking. There are no arbitrary flip-reset or combo bonuses.

## What the Discord example does and does not establish

The author describes a reach-time estimator applied to a predicted ball path,
then goals and stronger opponents. The exact reward is unpublished. They report
consistent touching at ~3 BILLION steps and Nexto results later, on a much
faster RTX4070/i9 laptop. This patch tests the useful idea without claiming to
copy the private formula or guarantee mastery at 500k. Our 500k checkpoint is
a bounded diagnostic, particularly since our initial actor is already trained.

RocketSim's C++ engine stays unchanged. A new physics engine is not justified
by the current evidence: a percentage accuracy claim would need a defined
collision/recovery/trajectory suite, and faster but wrong contacts can reduce
real-game learning. Benchmark reward/reset overhead before choosing further
optimization. CPU collection throughput and true learner SPS are distinct.

## Reproducing the preparation pilot

The optional `tools/contact_reward_pilot.py --steps 500000 --output <new-folder>`
compares a fresh small 64-wide CPU model under contact rewards with an identical
starting model under goal-only rewards, using the same drills and KL controller.
It opens no user checkpoints. This is a diagnostic, not a replacement for your
1.22M-parameter training run. `results/contact_pilot_results.json` includes all
four preparation pilots, including rejected versions and raw skill outcomes.
The final pilot improved over its control but did not reach the readiness gate
from scratch; the default experiment deliberately warm-starts your trained bot.
