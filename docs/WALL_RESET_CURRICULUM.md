# Native wall, air carry and reset practice

After selecting a starting model with the checkpoint selector, build the updated
native executable and start a separate run:

```cmd
cd /d E:\Downloads\Chat_GPT_AI
ATTENTION_NATIVE.bat build
ATTENTION_NATIVE.bat train --selection data\isolated\YOUR_SELECTOR_RUN\selection.json --curriculum wall-reset --run selected_wall01 --updates 1000
```

Use the actual selector report path printed by the selection command. This
example has a finite 1000-update budget and saves each update. Pause and resume
use the ordinary native attention commands; curriculum progress is included in
the checkpoint. The default mixture is half normal match arenas and half drill
arenas, with a smaller frozen-teacher anchor in drills. An explicit known model
can also be supplied using the trainer's `--source` option.

The native attention actor continues from the selected existing model. The
practice adapter changes reset states and rewards for designated drill arenas;
ordinary match arenas keep their original rewards. Frozen rivals remain neural
policies, with their existing kickoff script enabled. The learner receives no
scripted mechanic or kickoff controls.

The sequence is controlled wall roll, outward pop, airborne carry, genuine flip
reset, useful reset touch, and finish. Each transition is measured every physics
packet by `AttentionCurriculum.h`; rollout observations and controller timing
remain the original attention interface.

| Milestone | Required physical evidence | One-time or bounded reward |
| --- | --- | --- |
| Wall roll | Recent learner-ball contact, car and ball near the same side wall, at least two wheel contacts, upward car and ball motion, at least 120 units of new ball height | 0.5 milestone plus height progress capped at 400 units |
| Outward pop | Actual learner contact increases ball velocity away from the wall, followed within 0.45 seconds by separation from the wall above 300 units | 0.8 milestone |
| Air carry | Recent forward hitbox contact, airborne car and ball, close distance, compatible velocities, goalward ball motion, sustained control for 0.45 seconds, repeated contacts and over 120 units of progress | 1.2 milestone plus bounded controlled time and new progress |
| Reset acquisition | Spent flip becomes available, all four wheels report physics contact, all four wheel rays intersect the airborne ball, and car is away from ground and walls | 0.7 for the first acquisition, diminishing for repeats |
| Reset use | The verified or explicitly supplied reset is spent in a flip, followed within 0.45 seconds by a learner touch that increases goalward ball velocity and sends the ball in a useful attacking direction | 1.8 for the first use, diminishing for repeats |
| Finish | A real goal in the correct team's attacking direction | Modest ordinary goal reward plus a bounded verified completion bonus |

Time bonuses add at most 25% to milestone rewards. Initial stage deadlines are
7 seconds for the wall roll, 5 for the pop/carry/reset, 4 for reset use and 5 for
the finish. Difficulty can tighten those deadlines by at most 20%. Missing a
deadline stops further mechanic payouts in that episode; subsequent real goals
and concessions still count. No proximity reward is paid for merely following
the ball.

Repeated acquisition/use is limited to three pairs in an episode, with rewards
scaled by 1, 1/2 and 1/3. Repeated contact without spending and regaining a flip
cannot pay again. Goals terminate the reward tracker, so polling a goal state
cannot pay twice. Own goals receive a concession penalty and no completion
reward.

`HasFlipReset()` and `GotFlipReset()` alone are insufficient. RocketSim can set
them for a car that became airborne without jumping; stateset airborne cars can
also have these flags. The adapter requires a real spent-to-regained transition
and independent four-wheel ball geometry. A wall or floor landing cannot qualify.

Practice starts randomize both wall sides, learner team, position, velocity,
height and boost. Later-stage starts shorten the chain: for example, reset
acquisition starts a car with an already spent flip under an airborne ball;
reset-use practice deliberately supplies an available reset. Supplied earlier
steps unlock the remaining chain but earn no reward and never count as performed
wall rolls, carries or resets. Full-chain completion requires all preceding
events actually earned in that episode.

Retain normal matches alongside practice. Drill `success` means the current
target milestone was performed; it does not certify match strength, SSL skill or
mastery. Curriculum promotion should require enough completed drill episodes,
both teams and wall sides, and successes that start before the target milestone.
Checkpoint selection remains a separate matched match evaluation against the
protected baseline and diverse rivals.

Validation uses the actual pinned C++ RocketSim engine. Tests produce a physical
four-wheel reset from a spent flip, roll the ball up each side wall, verify goal
credit for both teams, reject real ground landing and false reset indicators,
check repeated reward caps, reject proximity-only carry, and step 120 randomized
practice starts. These establish event/reward behavior; they do not claim the
actor has already learned the mechanics.
