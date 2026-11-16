# Find the previously working CUDA runtime without reinstalling libraries

The earlier uploaded preflight identified E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe with Torch 2.9.1+cu126 and a GeForce GTX1650. The recent setup selected NovaForge's CPU runtime instead. That does not establish whether the old CUDA runtime is missing, fails import, times out, uses a mismatched Python ABI, or cannot access the driver.

The old finder ignored DuelForge's own runtime hint, capped candidates at 18 and suppressed probe failures. This patch includes current/historical hints, additional nearby .venv names and visible rejection reasons. It does not scan drives, install Torch/CUDA, read credentials or modify models.

Pause all trainers. Extract into E:\Downloads, merging chat_gpt_ai/duelforge. Run 31_RESUME_POTENTIAL_CUDA.bat again. It checks the formerly working GigaForge interpreter first and requires a real CUDA tensor operation before accepting a runtime. The existing actor/Adam/counters resume; no new reward fork or critic reset occurs. Failed CUDA-only discovery preserves the current runtime hint and writes runtime_probe_report.json instead of announcing CPU setup success.

If it still fails, send runtime_probe_report.json. It contains each tested path and the actual import/CUDA/timeout/ABI rejection reason, Torch's installation path and CUDA mask. The bounded search stops after approximately 90 seconds of probing; untested candidates are explicitly reported, not declared unusable. 30_DIAGNOSE_CUDA.bat gives an additional selected-runtime/driver report, cuda_diagnostic.json.

To inspect only the formerly working interpreter directly from CMD:

```
"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -c "import torch; print(torch.__version__, torch.__file__, torch.version.cuda, torch.cuda.is_available())"
```

No source-level fix can guarantee a missing or broken CUDA installation becomes usable. The report distinguishes that case from selection errors before any package/driver changes. Windows-native training requires CPython 3.11 x64; Colab uses its separate source-build setup.

Tests here used temporary files and simulated probe results to check saved/historical discovery, CPU rejection, preserved hints, CUDA admission, import failure and timeouts. A real CPU-only probe also rejected CUDA-only setup. Actual laptop CUDA availability remains a local check.

# Recovery objective idea

A useful next experiment is to include estimated time until useful control in interception reachability. Surface-relative orientation, retained momentum, boost cost and actual flip availability matter. Raw time-to-land can reward abandoning an aerial or wasting boost into the floor. No recovery reward is added by this runtime patch.

The pinned RocketSim code marks grounded state at three wheel contacts. That is not a general guarantee that any three-wheel contact on a ball restores a flip. A reset should be validated through the simulator's actual flip/jump availability after contact. Floor, wall, ceiling and ball contacts have different normals and trajectories. A useful recovery/reset should improve interception or scoring opportunities; repeatedly leaving and touching a surface should not earn an event bonus.
