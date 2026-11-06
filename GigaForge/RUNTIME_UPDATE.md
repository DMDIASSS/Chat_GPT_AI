# Quick dependency reuse and W&B fix

Pause training, then merge this update's chat_gpt_ai/gigaforge into the existing folder. Keep runs, checkpoints, models and native files. The update contains no heavy libraries or bot weights.

1. Open 12_FIND_LIBRARIES.bat for a read-only search and dependency_report.json.
2. Open 1_SETUP_GPU.bat. It now tries existing compatible Python/PyTorch installations first. It accepts working PyTorch 2.9.1 CUDA builds, including your already working 2.9.1+cu126, and verifies the actual GPU path. Use 0_SETUP_CPU.bat for CPU mode.
3. Open 3_START_OR_RESUME.bat. Every launcher now uses the same selected interpreter. Existing native01 checkpoints and W&B identity are preserved.

A complete compatible environment is used directly without pip installing anything. If a compatible Torch environment needs a smaller package repair, setup creates a separate child environment that references the existing site-packages and installs fixes locally. Donor package files remain unchanged. Keep that donor environment in place; moving or deleting it breaks the reference. A new runtime is selected only after verification succeeds.

When no compatible installed Torch exists, setup looks for local torch wheels and then uses normal pip download/cache handling. Python must be 3.11 x64 and Torch 2.9.1 to match the native executable. An installed CUDA toolkit alone does not replace CUDA-enabled Torch. Incorrect Python/ABI builds are reported and skipped. The finder does not combine DLLs from unrelated installations.

Search locations include this project, common Downloads/Desktop/Documents/Projects folders, common venv/Conda locations, registered Windows Pythons and CUDA toolkit directories. Discovery is bounded to eight seconds / 4000 directories / five levels, followed by timed interpreter checks. It skips models, runs, node_modules, Windows system folders and junctions. If a custom location is missing, set GIGAFORGE_SEARCH_ROOTS to semicolon-separated folder paths before running setup. GIGAFORGE_PYTHON can name a specific Python executable. This is dependency discovery, not a whole-drive disk cleanup tool; nothing is deleted.

The old GigaForge W&B pin was incompatible with NovaForge's SDK calls. Setup now follows novaforge/requirements-wandb.txt (currently wandb==0.31.0). FIX_WANDB_START3.bat repairs the SDK in the same runtime the launchers use, without reading or copying API keys. Existing SDK login is reused. Do not rerun the older third-party setup_runtime.py over this update: that would remove the finder integration, although its W&B pin correction is incorporated here.

No reward, PPO, model or opponent settings changed. Native verification also compares a promoted retained actor with the exact anchor loaded, so repeating setup after a promotion does not falsely compare a trained actor against the original parent.
