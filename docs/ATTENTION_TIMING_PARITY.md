# Native attention simulation contract

`GigaLearn_Project/Native_Attention/AttentionWorld.h` migrates the **match** branch
of `slater_versatile_env.VersatileEnv`. It owns RocketSim arenas and RLGymCPP game
states. It does not change the actor, action table, PPO objective, or match reward.

## Physics and policy timing

The reference engine uses `RocketSimEngine(rlbot_delay=True)`. Each packet:

1. Observes the current state and advances frozen Nexto clocks.
2. Simulates one physics tick using the controls already installed in the arena.
3. Installs the newly requested controls.
4. Reads the resulting state and evaluates the reward.

One learner action lasts eight packets. Its first physics tick uses the previous
action; the next seven use the new action. Commands saved as the observation's
previous action are the **newly emitted commands**, although the just-completed
physics tick used the delayed controls. Combining all eight packets into an
unqualified `Arena::Step(8)` changes both this contract and reward timing.

Every frozen opponent and teammate has its own source-matched `NextoV4Clock`.
Inference requests from all arenas can be batched before each physics packet.
The clock starts with `ticks=8, update_action=True`; consequently, its first eight
packets can request inference twice. Subsequent inference is on its own clock,
not necessarily on the learner's outer action boundary. During a scripted kickoff,
the script mutates both clock `action` and `controls`. Frozen inference observes
the clock's `action`; the remaining cars observe their last emitted commands.

The learner has no kickoff clock or script. Frozen kickoff uses the existing
standard-kickoff proxy: no previous touch, fewer than 168 episode ticks, ball
within one unit of midfield, and ball height below 100. This proxy is not an
authoritative RLBot kickoff-pause packet. The source's left-goes condition is
preserved exactly, including its counterintuitive branch.

## Reward and termination

The match potential is unchanged:

```
phi = .4 * learner_sign * ball_y / 5120
      - .12 * min(distance(learner, ball) / 5000, 1)
reward_each_physics_tick = .995**(1/8) * phi_next - phi_previous - .02/120
```

`phi_next` is zero at a goal. Useful learner contacts add `.05` when the ball's
velocity is goalward above 100; the existing more-than-30-tick gate and six-payment
cap remain. Actual goals give `+10` or `-10` relative to the learner team. Touches,
goals and experience from frozen players are not learner training samples.

The Python soccar goal threshold `abs(ball_y) > 5215.5` is used for termination.
Goal terminals do not bootstrap. Time limits remain truncations and **must**
bootstrap from the critic's value of the final state before reset. A goal has
priority over a time limit on the same packet. A terminal can occur before the
eight-packet action finishes; the actual physics count is reported.

## Common starts and simulator versions

The built-in reset uses the same five spawn positions, yaw angles, ball resting
height, grounded wheels and `33.3` boost as the Python kickoff mutator. It uses a
private seeded C++ RNG; `std::shuffle` is not Python `random.shuffle`. For paired
cross-framework trajectory tests, pass the Python permutation to `Reset`, or use
`ResetFromStates` with the exact same ball and car states. Car fixture ordering is
`blue-0..blue-N`, then `orange-0..orange-M`; arena iteration order is irrelevant.
All nine team size combinations from 1v1 through 3v3 are supported, but the first
training migration uses 1v1 matches.

The pinned GigaLearn checkout contains RocketSim **2.1.1**, while the current
Python package uses RocketSim **2.2.1**. Matching observations and scheduling
does not prove identical long trajectories across those versions. Any trajectory
comparison must record both versions and quantify position, velocity, touch and
goal differences. Performance comparisons must count learner decisions, physics
ticks and frozen inference separately and use common starts and policies.

## Verification

`tests/native_attention_world.cpp` runs real native physics and checks one-packet
control delay, eight-packet holds, partial timeouts, team-relative physical goals,
frozen-player isolation, and the unchanged reward formula. The optional pytest
wrapper also compares 190 frozen-clock packets directly with the Python source,
including script interruption and re-entry. These checks require native libraries;
they skip with an explicit reason when the C++ toolchain/build is absent.

Simulation arenas own independent mutable state and RNG. The caller may run
`Tick` in parallel across arenas after batching frozen inference. The reward,
clocks and game-state builder do not call Python or Torch.
