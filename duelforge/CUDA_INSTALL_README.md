# DuelForge isolated CUDA runtime repair

The diagnostic found Torch 2.9.1+cpu in NovaForge, a missing GigaForge GPU Python,
and a responding NVIDIA driver. This patch installs CUDA-enabled Torch in a new
DuelForge-owned environment; NovaForge's CPU environment is preserved.

1. Pause any trainer and close its console after its save finishes.
2. Extract this ZIP into E:\Downloads. Merge its chat_gpt_ai folder with your
   existing Chat_GPT_AI folder (Windows folder names are case-insensitive).
   Accept replacement of the included small launcher/Python files.
3. Open Chat_GPT_AI\duelforge\32_INSTALL_CUDA_RUNTIME.bat once.
   Keep internet connected. Pip reuses its download cache, but a missing CUDA
   Torch wheel requires a large download and several GB of free disk space.
4. Wait for CUDA_TRAINING_PROBE_PASS and CUDA_INSTALL_PASS.
5. Run 31_RESUME_POTENTIAL_CUDA.bat. Expect CUDA_READY and training on cuda.
   This launcher resumes potential01 for the existing 60-minute session limit.
   Run it again to resume after the session saves; Ctrl+C saves early.

Installation pins Torch 2.9.1+cu126, NumPy 2.2.6, and wandb 0.31.0. It installs no
CUDA Toolkit, driver, torchvision, or torchaudio. The PyTorch wheel supplies its
CUDA runtime. Existing W&B login handling remains in the trainer.

The installer uses .venv_cuda_291 (or a numbered suffix if that name is occupied
by an unowned environment). It never deletes another environment. An interrupted
owned installation can be rerun; pip reuses installed packages/cache.

Before selecting the interpreter, the installer tests a disposable project model
on CUDA with forward/backward/Adam, then runs the project's native verification.
It reuses the working collision-mesh asset path, without copying CPU libraries.
No trainer is started by installation. Existing actor, critic, optimizer, run
counters, rewards, and checkpoints are not reset or migrated by installation.

If installation fails, keep the console output and send cuda_install_status.json
from duelforge. If resuming fails, run 30_DIAGNOSE_CUDA.bat and send
cuda_diagnostic.json plus runtime_probe_report.json. Existing runtime hints are
only switched after successful native verification.

Verification performed while preparing this patch: official Windows CPython 3.11
cu126 index contains Torch 2.9.1+cu126; Python syntax checked; mocked installer
success/failure flows checked for environment preservation and selection gates;
ZIP integrity checked. No NVIDIA GPU is available on the preparation machine:
actual GPU execution and native Windows verification run on your PC in step 3.
