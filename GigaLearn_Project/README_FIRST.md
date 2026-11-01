# GigaLearn_Project — separate C++ research workspace

The newer tested setup is [Native_Backend/README.md](Native_Backend/README.md). It
builds CPU C++ PPO, supports replay pretraining/reset banks and bounded/resumable
runs. The older scaffold below remains separate.

**This is an integration/bootstrap scaffold, not an already trained GigaLearn bot.** Unpacked here:

`E:\Downloads\Chat_GPT_AI\GigaLearn_Project\`

All files created by C++ training use `GigaLearn_Project/checkpoints/` (process working directory); reports/logs go under `GigaLearn_Project/reports/`. The parent project's checkpoints are **scanned read-only** by `GL_0_CHECK.bat`. The framework's policy/observation architecture is **different from the native Nexto TorchScript actor**: it **cannot load or fine-tune Cycle 9** without a custom C++ policy and checkpoint conversion work. **Never rename or copy a .pt model as a GigaLearn checkpoint.**

## Windows instructions

1. Run `GL_0_CHECK.bat` (lists existing model inventory).
2. Install Git, CMake, Visual Studio 2022 C++ tools, CUDA toolkit and compatible LibTorch dependencies as required by the archived framework. The upstream README has **no complete installer instructions**.
3. Run `GL_1_GET_SOURCE.bat`. This fetches the publicly archived repository with its submodules into `GigaLearn_Project/upstream/` **on your PC**, not the parent project. No code or binary is downloaded until you choose this action.
4. Run `GL_2_PATCH_EXAMPLE.bat`. It backs up upstream's ExampleMain.cpp inside `cache/`, patches the hard-coded author mesh location to use `GIGALEARN_MESHES`, reduces default RAM load and substantially reduces reward-hacking incentives (especially touch/demo farming). If the archive changes unexpectedly, the patch refuses to run.
5. Set `GIGALEARN_MESHES` to an actual RocketSim collision-mesh directory using Windows environment variables; this project does not bundle them.
6. Run `GL_3_BUILD.bat`; if that succeeds, run `GL_4_START_CPP_TRAIN.bat` when prepared to start a **brand-new** C++ policy. It runs in a dedicated experiment directory and writes a persistent log.

Use **NVIDIA CUDA** for this specific GigaLearn sample when supported. Your older native Nexto TorchScript requires CPU due to its incompatible hard-coded CPU operation; that's a separate limitation.

Upstream https://github.com/ZealanL/GigaLearnCPP-Leak was archived by the owner. The README reports about 10x experience collection speed on the author's machine; that is not a benchmark on your PC. The repository's CMake expects CUDA/LibTorch/RocketSim subcomponents; individual environments may need manual configuration.

Training progress cannot be claimed until this actually builds, launches and completes rollouts in your Windows environment. Keep the original Cycle 9 unchanged.
