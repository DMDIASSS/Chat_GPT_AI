# CPU fallback in the supplied potential01 log

The log explicitly prints TRAINING: cpu. Earlier duel02 logs printed cuda. CPU neural inference and PPO account for much of the slowdown; the log does not reveal whether runtime selection, a CPU-only Torch installation, an explicit checkpoint device setting or CUDA/driver availability caused the switch.

Pause potential01 with Ctrl+C and wait for PAUSED_AND_SAVED. Extract this patch into E:\Downloads, merging chat_gpt_ai/duelforge. Run 31_RESUME_POTENTIAL_CUDA.bat. It rechecks bounded nearby existing runtimes with the current setup script, preferring CUDA, performs an actual CUDA tensor check and resumes potential01 with DUELFORGE_DEVICE=cuda. No Torch/CUDA package is installed or moved. If CUDA is unavailable it fails rather than requesting CPU training. The previous actor, Adam state, reward config and counters resume; there is no new reward fork or critic reset.

The runtime change adds an explicit execution-device override. Saved reward/model configuration is not edited; session records and logs show the actual selected device. The override is local to this batch-file invocation. The ordinary 23 launcher still follows its normal saved/auto device setting.

If it fails, run 30_DIAGNOSE_CUDA.bat and share cuda_diagnostic.json. This records the selected Python, Torch/CUDA build, GPU/tensor test, saved device setting and nvidia-smi result. It does not read credentials or dump the process environment. If setup fails to find a CUDA runtime in its bounded paths, use tools/setup_project.py --python with the exact known CUDA Python from the previously working project.

A CPU-only Torch build has torch_cuda_build=null. A CUDA-enabled build can still fail because of GPU/driver availability; the actual initialization error is included. Do not reinstall drivers or Torch merely from the TRAINING: cpu line.

The evaluation in this log was 10 wins / 32 draws / 6 losses against the trained parent, draw-adjusted score 54.17%, approximate 95% interval 43.1–65.2%. It is inconclusive. It appeared soon after the fork because the inherited counter crossed the next 2M validation boundary. The 34.82M counter includes parent experience; this log adds about 869k new learner transitions beyond the supplied 33,948,679-step parent.

Validation here: syntax checks, CPU override/fail-closed checks and diagnostics on a CPU-only server. No local GTX1650 or driver fix is claimed. Existing device-migration support normalizes Adam backend flags and step tensors; GPU resume itself still needs the user's CUDA runtime.
