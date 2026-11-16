# Implemented architecture — 0.2

## Scope and implementation decision

Fresh 1v1 Octane. The laptop preflight favored the 512-wide dense model over attention for this hardware: 1,216,091 total actor/critic parameters versus substantially slower attention updates in a synthetic test. Those timings did not measure Rocket League learning.

The native hot loop is C++ RocketSim: worker-pool stepping, observations, legal masks, reward components, true terminal states and auto-reset. PPO's fixed-horizon collector and tensor optimizer are readable Python using PyTorch/LibTorch, including CUDA on a compatible existing installation. This is deliberately narrower than the original all-native GigaLearn proposal. The archived GGL GAE path reproduced terminal/timeout errors; its optimizer was not imported into this trainer. See the preserved research audit. This implementation makes no million-SPS claim.

## Contracts

- Pinned RocketSim `c2baacb8f4b441dd8505e63c2aeb5a1679b60b02`; 120Hz physics.
- Eight-tick decision period (15Hz), seven ticks of previous controls then one tick of new controls per complete decision.
- Both cars use Octane; no hidden Breakout physics or scripted kickoff.
- 109 player-relative features, 90 GGL-style controller actions and a versioned DF90-v1 mask. Python/native action table and feature/mask parity are checked. RLBot's boost timer counts elapsed time; the adapter converts it to the simulator's remaining cooldown.
- Native outputs retain the true final state before resetting. Goal = terminal; episode/no-touch limit = timeout. Partial end-of-evaluation steps honor exact remaining physics ticks, including zero.
- Public packet-equivalent information drives inference. Internal jump clocks are diagnostic and do not secretly enter the deployed policy.
- Independent arena RNG streams do not depend on worker scheduling.

## Network and PPO

Separate actor and critic, each three 512-wide Linear → LayerNorm → ReLU layers. Actor has 90 masked logits; critic has one scalar. Small actor-output initialization preserves initial exploration. FP32; optional TorchScript compilation; CUDA fused Adam is probed before use, with a portable fallback.

Default 64 arenas, two native workers, two Torch CPU threads, 256 decisions per arena per rollout, two PPO epochs, minibatch 1024, learning rate 1e-4, gamma .995, GAE lambda .95, clip .2, entropy coefficient .01, value coefficient .5, gradient norm .5, KL stop .02. Model weights stay fixed during collection. Timeout values are computed from final states before optimization. Terminal rows zero bootstrap; timeout rows bootstrap once but cut the recursive GAE trace; rollout tails use the next state value. Advantages are normalized over learner rows only.

Frozen opponents never contribute rows to learner loss or learner-transition counts. History assignments change only at episode reset. Snapshots are immutable and rotating; active opponents are retained until no arena needs them. Current self-play uses both sides of the learner; history opponents use frozen policies. Optional Nexto uses a pinned adapter checked against upstream observations, logits and actions. It has no scripted kickoff in this project.

## Small reward hypothesis

`Phi(ball) = exp(-distance(ball, orange_goal)/3000) - exp(-distance(ball, blue_goal)/3000)` with goal centers `(0, ±5120, 200)`.

For blue: goal event ±1; potential `0.25 * (gamma * Phi(next) - Phi(previous))`; contact impulse `0.05 * contact_event * min(1, norm(delta_ball_velocity)/3000)`. Orange negates the goal/potential perspective and uses its own contact event. At a goal the next potential is zero; at a time limit the final physical potential is retained. The same gamma is used in PPO and shaping.

These are experimental objectives. A contact bonus can favor unproductive touches; the paired-seed pilot compares it with zero. Potential shaping is not a substitute for genuine outcome evaluation. There are no isolated rewards for jumping, air time, flips, resets, repeated combos or boost consumption. The bot must learn those controls through useful outcomes; this prototype does not claim it will discover advanced mechanics quickly.

## Evaluation, persistence and exports

Quick validation separates five kickoff geometries and varied open play, balances both colors with shared initial seeds and logs exact game rows. Match mode uses random standard kickoff resets after goals, draw at timeout, no overtime. Evaluation RNG uses a separate seed band. Discovery results and repeated best-candidate pins stay explicitly unverified. A paired-block approximate Student-t interval handles seed/color dependence; zero-variance samples use a conservative bounded fallback. No automatic champion promotion.

Checkpoints atomically store model, optimizer, config, Python/NumPy/Torch RNG, counters and snapshot references. A run lock prevents two trainers. A STOP request finishes the current fixed rollout/update. Every session is bounded and memory targets pause a completed update. The simulator restarts at resume with a recorded session seed; episode-level bitwise resume is not claimed.

Watch uses the exact learned actor in live native simulation. It can stream to RocketSimVis and always saves a bounded recent frame recording. The browser inspector shows what actually happened; it does not invent intentions from attention or value estimates. Reports contain source/config/results and bounded recordings, not credentials or weights.

RLBot v5 exports use a TorchScript .lt/.pt and an included Python adapter. Feature/mask/action agreement and a real SDK packet/clock roundtrip are tested. Actual Windows Rocket League client connection and match performance remain local verification. There is no v4 CFG export or pretrained strong actor in this release.
