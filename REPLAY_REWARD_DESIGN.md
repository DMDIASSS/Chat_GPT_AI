# Reward-design notes for the replay model

Source read: ZealanL's [Rewards](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/rewards.md)
and [Making a Good Bot](https://github.com/ZealanL/RLGym-PPO-Guide/blob/cef4469986d8147cc9071af2b561917790ac00ae/making_a_good_bot.md),
at guide commit `cef4469986d8147cc9071af2b561917790ac00ae`.
The guide describes empirical PPO training advice, and marks parts as work in
progress. Its old RLGym API examples should not be pasted into this RLGym v2
project without adaptation.

## The current model

This run is supervised imitation, with action-token cross-entropy and value-head
regression. Value labels come from the recorded next goal, discounted with a
15-second time scale. It has no hand-written penalty for retreating, driving
backward, leaving the ball or spending boost. This optimization update does not
introduce PPO or alter those targets or any training files.

The planner also subtracts a value-disagreement term and adds an action-prior
term. Those can influence conservative decisions even without a movement reward.
They are heuristics, not proof of calibrated risk. More search candidates can
also expose value errors; lower inference latency alone establishes no strength
improvement. Changing those weights needs controlled gameplay evaluation.

## Applying the guide if an RL stage is added later

- Do not penalize moving away from the ball by default. Rotation, saves, boost
  routes and getting behind the ball require it. The guide's speed-to-ball
  example returns zero when moving away rather than assigning a negative reward.
- Do not replace a forward-only reward with an unconditional reward for moving
  the ball away from an opponent. Distance can grow while the ball goes into our
  own goal, and repeated retreat/re-approach cycles can farm the signal. Prefer
  demonstrated possession, a useful outplay or a better future scoring chance.
- Balance auxiliary encouragement against outcomes and exploration. Huge concede
  penalties can promote passivity; the guide's proposed aggression bias is a
  tunable experiment, not a reason to erase defensive incentives. Likewise,
  excessive boost preservation can teach hoarding, and air rewards can teach
  pointless jumping. Positive-only rewards can still be exploited.
- Use team outcomes and appropriate shared credit in 2v2/3v3 so teammates are
  not paid to fight each other for every touch. Phase in auxiliary weights based
  on measured behavior rather than copying all beginner rewards into a model
  already trained on strong demonstrations.
- If using potential-based shaping, use `gamma * Phi(next) - Phi(current)` with
  the learner's discount and correct terminal handling. Its policy-invariance
  assumptions do not automatically hold after clipping, dropping negative
  differences or mishandling time-limit truncation.

Before a long RL run, evaluate the reward components on retreats, saves, boost
use, possession, teammate support and adversarial loops: circles, repeated soft
touches, jumping in place and oscillating the ball. Then measure held-out matches
against frozen opponents on paired seeds and both colors. Rising reward or
falling training loss is insufficient evidence of improvement.

No reward implementation or new training run is supplied by this inference patch.
