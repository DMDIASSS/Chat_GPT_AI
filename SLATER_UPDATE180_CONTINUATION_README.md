# Continue the capable model directly

Pause other training to avoid competing for CPU/GPU resources. Extract the diagnostics update into `E:\Downloads\Chat_GPT_AI`, then run `SLATER_20_CONTINUE_UPDATE180.bat`. It requires your actual `data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt`; it fails if missing and never substitutes Nexto or a native MLP.

This uses the existing RocketSim/PyTorch attention trainer. All starting actor tensors are checked against the frozen source before optimization. The actor inherits update180; the versatile critic and optimizers start fresh. Original weights stay protected. Frozen update180 and Nexto opponents have scripted kickoff; the learner's kickoff remains learned. The teacher anchor starts at update180 and changes only after a confirmed promotion.

The task mix emphasizes matches, ground scoring and defense. Actor LR is 3e-6, teacher anchor 0.10, per-update KL target 0.005. These are conservative experiment settings, not evidence of superior performance. Three cycles run per launch, with at most 12 cycles total and a stop after three unsuccessful cycles. Every update is preserved. Re-running the same launcher resumes the saved run/settings. `SLATER_20_PAUSE.bat` requests a checkpoint-safe pause; wait for `VERSATILE_PAUSED`. `SLATER_20_STATUS.bat` shows latest and selected checkpoints.

Results are in `data/isolated/versatile/update180_continue01/`: `selected.json` identifies the retained baseline or promoted model, `progress.json` gives latest, and `evaluations` contains matched screens, independent confirmation seeds and skill retention checks. Rejected models are preserved. The latest model is not automatically the best. These finite simulator checks do not guarantee competitive rank.

Human replay gradients are OFF unless a compatible attention dataset is supplied explicitly. Native `.bin` banks cannot be used directly. To reuse an existing attention dataset containing `q.npy`, `kv.npy`, `target.npy` and `manifest.json`, start a new run:

```bat
.venv\Scripts\python.exe -u slater_continue_update180.py run --run update180_human01 --dataset "data/isolated/YOUR_ATTENTION_DATASET"
```

The dataset hashes, shapes and replay-disjoint partitions are validated before training; accepted replay BC runs every four updates alongside PPO. If you only have raw replays or the native event bank, use the existing versatile prepare command to create the attention-format dataset first. Do not spend another night parsing before checking the audit and current model behavior.

Cloud verification uses the available original Nexto attention checkpoint, because your local update180 was not uploaded. It verifies exact actor inheritance and the existing trainer's actual optimization/evaluation behavior; it does not claim an update180 improvement was measured in cloud.
