# DuelForge 0.4 — interception-potential experiment

## What your 33.9M-step diagnostic establishes

Your learned actor passed side rotation and action/mask agreement. The frozen random initial policy selected reverse on all five kickoffs. That explains the old orange behavior. It does not diagnose why the trained policy sometimes turns away just before a touch.

At 33,948,679 learner transitions the V2 approach/contact bootstrap is already zero: it faded by 20M. The old small contact-impulse term remains in that run. The new experiment changes the reward definition in a separate fork; it does not edit duel02 or silently change its saved config.

## Run this on Windows

1. Pause the current trainer and wait for PAUSED_AND_SAVED. Close Python and viewer consoles so Windows can replace the native .pyd.
2. Extract the ZIP into E:\Downloads. Its included chat_gpt_ai/duelforge folder merges with your existing project. No runs, weights, environments or exports are bundled or removed.
3. Run **7_VERIFY.bat**, then **23_START_POTENTIAL_EXPERIMENT.bat**. This requires an existing compatible runs/duel02/latest.pt; no random replacement is created.
4. First start creates **runs/potential01** from the current paused duel02 checkpoint. The actor and its Adam moments are preserved exactly. The critic and its Adam moments reset because the returns have changed. Learning rate is reduced to 5e-5; entropy stays at .003. Arena/rollout settings, features, masks, action table and timing come from your saved parent. Its counters continue, rather than pretending this is a zero-step actor.
5. Training is capped at 60 minutes per invocation. Start with **30 minutes**, then pause using Ctrl+C or 2_PAUSE.bat. Resuming 23 continues the existing experiment; it never recopies the parent or resets the critic again.
6. Run **24_WATCH_POTENTIAL_VS_PARENT.bat**. Blue = new potential experiment, orange = the trained duel02 checkpoint frozen at fork time. Both Octane. Run **25_REPORT_POTENTIAL.bat** afterward and send its report ZIP.
7. **26_EVALUATE_POTENTIAL_VS_PARENT.bat** runs 200 balanced-color games of 100 simulated seconds against that exact trained parent, draw at timeout. **27_EXPORT_POTENTIAL_V5.bat** exports the candidate using the existing verified TorchScript reader. Run the exported INSTALL_V5 and DIAGNOSE scripts before importing bot.portable.bot.toml.

Menu 23–27 provides the same operations. The original 17/18/19 continue to refer to duel02, so use the new files for this experiment. 21 watches trained duel02 vs itself; 22 checks its side symmetry.

No better-playing claim is made from engineering tests. The short server pilot verified the pipeline, not improvement of your unavailable local 33.9M actor. The fork records the actual source hash and preserves the trained parent for every comparison. Nothing automatically promotes the candidate. Automatic discovery evaluation pauses this experiment if its upper 95% score bound falls below 45% against the parent; small panels cannot detect every regression.

## New objective

For a shared forecast of the moving ball, estimate each car's first feasible interception time. Turning, current momentum, forward/reverse acceleration, finite boost, height, jump availability and demolition state constrain the estimate.

`interception = tanh((T_orange - T_blue) / temperature)`

The additional goal-threat term looks for predicted crossings of a goal mouth and discounts a crossing when the defender's estimated interception comes first. It describes the ball's existing trajectory; it does not claim to predict every possible future shot or possession sequence.

`Phi = clip(0.8 * interception + 0.2 * goal_threat, -1, 1)`

`r_blue = goal_differential + 0.5 * (gamma * Phi_next - Phi_current)`

Orange receives the exact opposite reward. The same decision-level gamma is used by PPO and shaping. A true goal uses absorbing Phi_next=0. Time limits retain the final physical Phi and bootstrap the final-state critic value. Reset states initialize the next episode's potential and never enter the preceding transition. Zero-tick evaluation rows pay zero.

There is **no direct reward for touching, impact speed, approach speed, jumping, flipping, reversing or being airborne** in this experiment. Old native ball-position shaping is discarded; impulse is configured to zero and the V2 bootstrap is disabled. Persistent shaping depends on the state potential and does not fade away at 20M steps. A faster touch matters when it improves the estimated interception race or goal threat. Slamming the ball hard toward our own goal should not earn a speed bonus.

Correct shaping algebra preserves the discounted underlying objective under its assumptions; it does not guarantee fast finite-budget learning. An inaccurate potential can still make learning worse. Temperature, interception/threat mixture and shaping weight are explicit switches in the saved predictive config; change them in a new experiment, not silently during resume. The native goal-progress parameter remains in the legacy config for compatibility but is not part of the predictive reward.

## Estimator scope and limitations

The production estimator is C++ with a NumPy reference and parity tests. Ball prediction includes gravity, drag, angular velocity, radius-aware plane bounces and contact friction/spin transfer. In four limited two-second RocketSim fixtures, maximum ball-position errors were approximately 0.45, 2.72, 27.66 and 4.68 Unreal units. This is not a global Rocket League accuracy percentage. Rounded corners, ramps, posts and complex repeated contacts are not faithfully modeled; a geometry warning is logged, not an accuracy certificate.

Car reachability is a kinematic envelope with finite boost and turn delay, not an exact first-touch solver. It does not model every flip impulse, wheel transition, wall-driving path or recovery controller. Airborne feasibility can be optimistic or conservative. There is no selective full-car physics refinement in the training reward in this version, no complete shot-opportunity search, and no replay-state curriculum. The implementation does not claim those unbuilt parts of the earlier large brief.

The predictor is deterministic from the current supplied state; there is no stale prediction cache. Native/reference tests, absorbing-terminal and timeout tests, side antisymmetry, boundedness, telescoping, boost/turn/height cases and exact actor-fork checks are included. Full-size train/resume/watch/evaluate/export/report smoke checks passed. Actual RLBot client gameplay remains a local test.

## Performance and diagnostics

One short CPU full-PPO integration check measured about 6,030 learner transitions/s for the control and 5,904 for this objective, approximately 2% lower. This is not a GTX1650 or T4 speed claim. Raw collection timing has a different scope; all results are in results/ and VALIDATION.json.

Run **28_BENCHMARK_POTENTIAL_COST.bat** to measure four disposable full-PPO updates per objective with your arena/rollout/model settings. Your actual weights and run config are untouched. Ctrl+C cancels. It creates scratch checkpoints in benchmarks/ and saves results/potential_cost_local.json. Speed alone does not establish sample efficiency.

Training logs add estimated interception time, unreachable fraction, geometry warnings, interception advantage, goal threat and reward cost. The frame inspector also shows estimated interception times for both cars and the before/next potential used for the reward. Estimates beyond the search horizon are labeled accordingly. Watch now saves contact_diagnostics.json: episode-aware close-approach windows and whether a real simulated contact follows. These are heuristic windows, not a certified whiff counter or proof that a steering command was wrong. Reports include the last two bounded recordings and diagnostics. Please record an example of the last-second turn using 24 before making report 25.

## Colab/Linux

The same core PPO, observations and checkpoints are used. Copy the included duelforge project to /content/duelforge without an extra nested chat_gpt_ai folder. Run `bash colab/0_SETUP.sh` to build an interpreter-compatible native .so from pinned RocketSim and the new estimator. An existing older module without predictive_estimate is rebuilt. Setup reuses installed Torch; it does not replace it with RocketChad3 or attempt the failed RocketGPU CUDA build.

Run `bash colab/23_START_POTENTIAL_EXPERIMENT.sh`; 24 records headless gameplay; 25 reports; 26 evaluates; 27 exports. Colab storage is ephemeral: preserve the entire parent and candidate run folders in your own Drive/download process before ending the runtime. No mounted Drive or Colab GPU was available for end-to-end testing here. Python/PyTorch/NumPy versions must be compatible when moving training checkpoints across machines. Live RLBot testing belongs on the Windows PC.


## Named ablations

`tools/fork_potential.py` creates another named fork with configurable potential weights. It never starts training or changes an existing run. With your selected Python, for example:

```
python tools/fork_potential.py --source duel02 --run intercept_only --intercept-weight 1 --threat-weight 0
python run.py train --run intercept_only --minutes 60
```

Weights 0/0 give a goal-only control; 1/0 tests interception alone; .8/.2 is the default mixture. Keep network, initialization parent, experience budget and evaluation protocol matched. Each fork reinitializes its critic deterministically and preserves the same parent actor. Changing the current potential01 config file does not retune a saved checkpoint.


Research basis: Ng, Harada and Russell (1999), Policy invariance under reward transformations: https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf . The theorem justifies the discounted potential-difference form under its assumptions; it does not validate the interception heuristic or guarantee finite-budget improvement.
