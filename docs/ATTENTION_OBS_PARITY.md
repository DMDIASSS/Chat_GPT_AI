# Native attention observation contract

`GigaLearn_Project/Native_Attention/AttentionObs.h` ports the original Nexto
observation builder and the current corrected `slater_team_env.TeamObserver`.
It keeps the existing attention actor's inputs; it does not flatten these
entities into an MLP observation.

## Collector interface

```cpp
SlaterAttention::PreviousActions previous;
SlaterAttention::AgentLabels labels;
auto observations = SlaterAttention::AttentionObs::BuildAll(state, previous, labels);
SlaterAttention::FlatBatch batch;
batch.Reserve(observations.size());
for (const auto& observation : observations) batch.Append(observation);
```

`state` is the actual `RLGC::GameState` from the native world. Previous actions
are eight actual controller values, keyed by RocketSim car ID. Labels are the
canonical Python agent names, for example `blue-0` and `orange-1`. Supply those
labels when comparing with Python or assigning team roles; without labels the
builder sorts string representations of car IDs within each team.

The outputs are contiguous float32 buffers with shapes `q[B,1,32]`,
`kv[B,41,24]`, and `mask[B,41]`. There are six player slots, then the ball,
then 34 boost pads. All nine combinations of 1..3 players on each team share
this layout. Rows are sorted blue team first, then lexically by agent name.
`FlatBatch::carIds` preserves that row mapping; different arenas can have the
same car IDs, so the collector also needs its arena/row index mapping.

For frozen scripted opponents, pass the scheduler's previous *policy action*
when preparing its next policy inference, matching the Python source clock.
Actual simulated controls and the policy action can differ during kickoff.
For the raw learner, pass its actual preceding policy controller action.

## Features preserved

- Query features contain the learner's normalized world state, with orange
  coordinates inverted, plus the eight previous controls.
- Entity positions are relative to the query. Entity velocities are **not**
  made relative; the legacy builder only subtracts query position.
- Positions, velocities, forward/up bases and angular velocities rotate in
  the XY plane using the original `atan2(forward_x, forward_y)` convention.
- Position/velocity normalization is 2300; angular velocity normalization is
  5.5; car boost is converted from 0..100 to 0..1.
- Orange observations invert X/Y of all vector groups and swap teammate and
  opponent flags. The self row also retains its teammate flag.
- Rotation matrices pass through the same double-precision quaternion round
  trip before producing forward and up vectors.
- Fixed boost-pad positions match the vendor's list, including its asymmetric
  `(-940, 3310, 70)` entry. Using another field list would alter the policy.
- Absent player slots have exactly zero features and additive mask `-10000`;
  every real entity has mask zero.
- Flip availability follows the RLGym v2 `has_flip` property. It is not the
  native `HasFlipOrJump()` shortcut, which also returns true on the ground.

The current vendor builder declares `demo_timers` and `boost_timers` but does
not update or consume them. Its demo feature is the demolition boolean and
its boost feature is the availability boolean `cooldown <= 1e-6`. The native
port preserves this actual behavior. It does **not** invent countdown inputs.
Observation construction is therefore stateless and does not advance time
when the collector observes several players from the same simulation state.

## Actual parity verification

`ObsParity.cpp` loads serialized physical state payloads into `RLGC::GameState`
and writes observations produced by the same header used by the collector.
No C++ simulator replay is involved in this check: that isolates observation
correctness from the Python/native RocketSim version difference.

`tests/native_attention_obs_fixtures.py` generates **108 real RocketSim states**:
all nine team rosters, kickoff, moving ground play, airborne play, upside-down
recovery, demolished cars and boost cooldowns, each before and after eight
physics ticks. It checks every player, for **432 views across both colors**.
It includes used/expired flips, nontrivial linear/angular velocities and
rotations, shuffled roster entries, lexical agent ordering, missing prior
controls and nonzero discrete actions.

On the cloud CPU validation run:

| Comparison | Maximum absolute difference |
| --- | ---: |
| Query features | 2.22e-16 |
| Entity features | 2.78e-16 |
| Masks | 0 |
| Original Nexto actor logits | 0 |

All 432 greedy action choices matched. Four integration tests passed,
including invalid-control rejection. These measurements establish the port's
observation and policy-input compatibility, not a stronger trained model.

Run with a CMake-built parity executable:

```cmd
set "SLATER_ATTENTION_OBS_PARITY_BINARY=path\to\SlaterAttentionObsParity.exe"
.venv\Scripts\python.exe -m pytest tests\test_native_attention_obs.py -q
```

On Linux the tests also compile `ObsParity.cpp` using g++ and the patched
pinned GigaLearn checkout. `SLATER_GIGALEARN_SOURCE` can point to that checkout.
The original observation source and its upstream CC BY-NC-SA 4.0 attribution
remain in `vendor/nexto/nexto_obs.py` and `vendor/nexto/LICENSE.txt`.
