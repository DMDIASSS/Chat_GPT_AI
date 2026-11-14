# AttentionForge 0.2 — laptop update

This is an in-place update for AttentionForge 0.1, **not another unrelated framework**. It preserves `runs/attention01`, its config, checkpoints, history and exports. Existing launchers still address that run. The new menu uses a separate fresh run, `laptop01`.

## Install and use

1. Pause training and wait for `PAUSED_AND_SAVED`. Close watch/trainer Python processes before replacing the native module; Windows cannot replace a loaded `.pyd`.
2. Extract this ZIP into **E:\Downloads**, merging `chat_gpt_ai\attention_forge` with your existing folder. Overwrite the included program files. No runs, runtime pointer, saved keys, local paths or environments are included in the update.
3. Run **SETUP.bat** to verify the selected existing runtime and new native module. No new Torch, CUDA or RLGym installation is required when your existing setup works.
4. Open **LAPTOP.bat**, choose **1**. First start runs bounded timing probes on your PC, writes `laptop_tuned.json`, then starts **laptop01 from random weights**. Keep the console open. Probe weights are discarded. The menu keeps the saved run configuration on later resumes; it never retunes an existing run behind your back.
5. Let the first full updates finish. Look at **end-to-end learning transitions/s**. The tuner's displayed learning SPS is an **estimate** from short collection and optimizer probes; actual training logs measure full updates. Ctrl+C while training requests a graceful save and returns to the menu. Then choose **2** to watch, **4** for a report, **3** for evaluation after the first history snapshot.

The first tuning pass tests 32/64/128 arenas, then two worker/thread alternatives around its initial timing winner. It changes arena/CPU worker settings only. FP32, 1.09M network size, tick skip eight, one-tick action delay, two PPO epochs and minibatch 256 remain fixed. Arenas within 5% of the timing winner are preferred if they use fewer resources. This is a small heuristic benchmark, not an exhaustive search or a playing-strength test.

Expect the first setup/tuning to take longer than an ordinary resume. If you prefer no tuning, copy `laptop_config.json` to `laptop_tuned.json` before starting. The supplied template uses 32 arenas and four native workers. Do not modify the saved config of a running or existing run; use a new run name for a different experiment.

## Model and rewards

- **1,091,163 parameters**, width 256, four heads, two ego-query attention blocks.
- Fresh **1v1 Octane** self-play and historical opponents. No teacher, replay retrieval, hive selector, scripted kickoff or automated reward search.
- Three standard reward definitions: RLGym **GoalReward**, RLGym-tools **VelocityPlayerToBallReward** (positive-only) and **AdvancedTouchReward** (boolean touches, no acceleration bonus). Weights 10 / .2 / .02. These weights are a starting hypothesis, not an official proven preset.
- They are small **native ports**, tested against the actual upstream Python classes; Python reward objects are not recreated during simulation. The old custom potential/possession terms are absent from this profile's reward. See `REWARD_SOURCES.md` for definitions, versions and attribution.

## Execution changes

C++ observation construction matches the portable encoder. The existing attention architecture and parameter names are preserved. Collection uses standard exponential-race categorical sampling, one packed device-to-host transfer and batched timeout bootstraps. A bounded optional FP32 GPU rollout cache reuses observations across PPO epochs; it is skipped when the memory budget does not fit. Numeric precision, simulation timing, reward signal, terminal handling and gradient checks are not relaxed for a speed score.

Existing attention01 weights remain loadable by the optimized implementation. Its original config/rewards are retained. Only laptop01 uses the larger model and standard reward profile. The two architectures cannot directly exchange weights, so the new model starts fresh.

## Reports and expectations

The report includes full-update timings, collection/PPO times, optimizer minibatch count, tuning measurements and configs. W&B uses the existing login and project `attentionforge`, with run name `laptop01`. No keys are displayed or included in reports.

Use the first 30–60 minutes as a health/progress check, then pause and send menu **4**'s ZIP. Compare actual touches, goals and frozen-opponent results over longer runs. A larger model and higher SPS do not certify stronger play. The short validation runs are implementation checks, not trained strong weights.

RocketChad3 and RocketGPU were inspected; RocketGPU's CPU backend was built and benchmarked here. **RocketChad3 GPU training was not tested on your GTX 1650.** Its high-end example is not automatically installed. See `FRAMEWORK_REVIEW.md`. Existing GigaLearn 20–40k SPS is a useful target; this release does not promise that rate with a different attention model and workload.

Export remains TorchScript **PT + CFG for RLBot v4**. Native watch shows the actual latest policy in both teams. RLBot v5/TOML/LT remains outside this release.
