# AttentionForge 0.3 — GPU execution update

Your console output shows that training started successfully. Its rollout timing probes reached about 19–21k player decisions/s, while full updates ran around 3.3k new learner transitions/s. This indicates significant PPO/update overhead; the log alone cannot identify CPU dispatch vs GPU compute as the cause. CPU-wide utilization or a Task Manager 3D graph also does not measure CUDA compute utilization reliably.

## Install and resume with the same training settings

1. Press **Ctrl+C** in the trainer and wait for **PAUSED_AND_SAVED**. Close the Python trainer/watch/menu processes before extracting program files.
2. Extract the ZIP into **E:\Downloads**, merging `chat_gpt_ai\attention_forge`. No configs, trained weights, environments, CUDA libraries or native DLLs are replaced by this patch.
3. Open **LAPTOP.bat → 1**. It resumes the current **laptop01**, including model, critic, Adam moments, step values, counters, history and W&B ID. It does not restart from random weights.
4. The first CUDA start benchmarks eager vs TorchScript forward/backward on disposable model copies. TorchScript is selected only if its measured minibatch time is at least 5% lower and the loaded model's logits/values agree. Otherwise it keeps eager execution. The optimizer probes fused Adam on a disposable tensor and falls back to foreach Adam if necessary. CPU execution stays eager by default.
5. Read the new update line: **collect Xs / PPO Ys / cache GPU-or-host**. After a few updates, pause and make a report with menu **4**. It includes the chosen execution backend, optimizer backend, memory peak and all timings.

The native physics engine still runs on the CPU. This patch improves how training work is submitted to the GPU. It does not install RocketChad3 or move physics to a GPU simulator.

## Give the GPU larger useful training batches

If PPO dominates the update time:

1. Pause the current trainer and close it.
2. Run **GPU_PROFILE.bat**, or choose menu **8**. It uses copies of your **trained checkpoint**, tests optimizer minibatches **256, 512 and 1024** plus the current size, and applies a conservative GPU-memory budget. Probe weights are discarded.
3. It creates **runs\laptop01_gpu** with the **same trained model, optimizer moments, baseline, history and step counters**. The original `laptop01` checkpoint is not changed. The new run records the parent model hash and all configuration changes.
4. Open **GPU_RUN.bat → 1** to continue that experiment. Its menu's watch/evaluate/report actions address `laptop01_gpu`. W&B starts a new run ID, named `laptop01_gpu`, at the inherited transition count. The original LAPTOP.bat continues to address `laptop01`.

If `laptop01_gpu` already exists, the profiler refuses to overwrite it. Use GPU_RUN.bat to resume/watch/report it. For custom names use `_RUN.bat gpu-profile --run <source>` and `_RUN.bat laptop --run <source>_gpu`.

Larger minibatches reduce the number of optimizer steps per epoch and **can change learning**, even though both PPO epochs still visit the same collected samples. This is why they are a separate experiment, not a silent edit of your current run. LR, reward weights, observation contract, architecture, tick skip and action delay are preserved. Timing selects execution settings, not a champion bot; held-out match results are still needed to assess strength.

## Changes and limits

- CUDA fused Adam, checked before touching trained weights; saved implementation flags are normalized after loading so moments and steps resume correctly. CPU models remain compatible with checkpoints saved on CUDA.
- Optional TorchScript execution selected by a local forward/backward timing probe. Parameter identities and state-dict keys are preserved, so the existing optimizer updates the same weights.
- One pre-update GPU-to-host health check for loss, KL and gradient norm. Finite checks, gradient clipping and the KL stop remain active **before any optimizer update**. A rejected minibatch may perform backward computation, but it never calls optimizer.step.
- PPO timings now include creation/upload of the resident rollout cache. Actual optimizer minibatch counts and selected execution modes are logged.
- New report entries: `execution_profile.json`, `gpu_batch_profile.json` and, for the new experiment, `fork_provenance.json`.

No BF16, AMP, training-epoch reduction, larger physics timestep, artificial GPU stress work or system power-setting change is introduced. GPU measurements require your actual CUDA machine. CPU correctness checks here do not establish a GTX 1650 speedup, and no 20–40k full-training SPS claim is made.
