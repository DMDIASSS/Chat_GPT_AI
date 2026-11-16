# Fresh reward hypotheses, not the previous bot's recipe

These are proposals with a tested mathematical reference in tools/reward_reference.py. They have NOT been validated in learning or transferred into a complete trainer. Reward magnitudes are deliberately dimensionless. No list of mechanics, teacher reward guesses or old project configuration is inherited.

Let team 0 be blue, attacking +y. Let g+ = (0,5120,200), g- = (0,-5120,200), b be the ball position, and R=3000 UU. Let gamma be the SAME per-decision discount as PPO.

## 1. Goal outcome

`r_goal_i = +1` when team i scores, `-1` when the other team scores, otherwise 0. Use the scoring team, not last-touch ownership; own goals are therefore handled correctly. A goal terminates the training episode. Full match W/D/L and goal differential remain the external evaluation objectives.

Intention: reward scoring and punish conceding. Risks: sparse early discovery; goal differential is not identical to optimal clock management in a full match. No overlap with transient contact bonus. Instrument scoring team, scorer/last-touch IDs separately, goal speed, match score/time and event tick. Test own goals, color rotations, terminal values and goal/reset ordering.

## 2. Bounded ball-to-goal potential

`Phi_blue(s) = exp(-||b-g+||/R) - exp(-||b-g-||/R)`; `Phi_orange = -Phi_blue`.

`r_potential_i = 0.25 * [gamma*Phi_i(s_next) - Phi_i(s)]`.

Set Phi at a TRUE terminal to zero. Do not zero Phi merely because collection ends or an artificial timeout occurs; use the pre-reset physical next state and critic bootstrap. Per-decision gamma must not be mixed with per-physics-tick potential evaluation.

Intention: provide a cheap geometric gradient toward a more favorable ball location. This is not a learned chance of scoring and does not know who can intercept. Pure potential shaping has a policy-invariance rationale under its assumptions, but it neither guarantees fast discovery nor solves nonstationary self-play. [Ng, Harada & Russell](https://wordpress.andrewng.org/index.php/publication/policy-invariance-under-reward-transformations-theory-and-application-to-reward-shaping/).

Risks: bad geometry may temporarily favor hopeful clearances or advance without possession; incorrect terminal/reset math creates farming. It overlaps with goal-progress heuristics, so do NOT add velocity-to-goal, shot-angle and possession potentials on top without separate ablations. Instrument old/new potential, discount, terminal type and weighted contribution. Tests check telescoping, symmetry and timeout handling. Later remove it in a matched ablation if it contributes no useful learning improvement.

## 3. Contact-gated impulse bootstrap — experimental arm only

`r_impulse_i = lambda * 1[car i physically touched during the decision] * min(1, ||v_ball_next-v_ball_before|| / 3000)`.

Initial A/B arms: lambda=0 and lambda=.05. Do not infer touch from distance. Wheel/roof/body contact counts according to actual simulator contact telemetry. If the ball changes velocity without a touch, this term is zero. Record simultaneous/opponent contacts, because assigning the whole interval's velocity change to a contacting car can be imprecise.

Intention: help discover effective ball contacts from random initialization. Risk: wall-banging, repeatedly hitting away from goal or double-crediting collisions; a strong impulse is not inherently useful. This term changes the objective and has no policy-invariance claim. It is small and contact-gated, but that alone does not prevent exploitation. It overlaps with other touch-strength rewards, so no flat touch, aerial-touch or combo rewards are added. Instrument touch IDs, delta velocity, ball direction and whether the next few seconds produced a goal, a lost possession or an opposing shot. Compare to lambda=0 under the same seeds/compute before retaining it; do not add a hidden automatic schedule.

## Exploration, recovery and defense

No positive reward for simply jumping, flipping, being airborne, doing a reset or touching a surface. Keep the full useful jump/flip action set and stochastic exploration. If jumping disappears, inspect masks, entropy and elevated-target evaluations before inventing an airtime bonus. A simple distance-only “possession” ratio can favor passive chasing and is not adopted without evidence.

Defense/recovery measurements are initially diagnostics: goals conceded after failed challenges, time back to controllable orientation/momentum, useful follow-up actions, successful early saves, boost expenditure and whiffs. A recovery potential or predicted interception advantage is a later one-variable experiment, not a claim that a static distance calculation proves a save is reachable. A fixed negative reward for air time or every missed contact could discourage necessary challenges and is excluded.

## Acceptance

Run invariants first, then small paired-seed A/B pilots. Compare actual contact rate, touches directed away from own net, non-kickoff goals, concessions, boost usage and selected gameplay clips, followed by balanced-color matches. Reject a term that increases training reward while worsening independent match outcomes. When performance is too weak for a meaningful W/D/L comparison, say so; drill success alone is not competitive strength.
