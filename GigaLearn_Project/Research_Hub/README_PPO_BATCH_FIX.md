# GigaLearn Research Hub: PPO batch fix v1

The first Research Hub release had a mismatched PPO configuration: `cfg.ppo.batchSize=5000` and `cfg.ppo.miniBatchSize=2048`. GigaLearn requires the former to be evenly divisible by the latter, and correctly refused to start before training.

## Install

1. Exit Research Hub training if active and **back up your `GigaLearn_Project` directory**, especially `build_py311/checkpoints/4562496`.
2. Extract this ZIP into `E:\Downloads\Chat_GPT_AI` preserving folders. Replace `hub_core.py` and `hub_cpp_patch.py` when asked. The previously fixed `utf-8-sig` code is included.
3. Double-click `GigaLearn_Project\Research_Hub\HUB_FIX_PPO_BATCH.bat`. It changes **only** `upstream\src\ExampleMain.cpp` and preserves the original as `ExampleMain.cpp.before_ppo_batch_fix_v1.bak`.
4. Rebuild in **x64 Native Tools Command Prompt for VS 2022**:

   ```cmd
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub
   BUILD_IN_VS2022_DEV_PROMPT.bat
   ```

5. Open Research Hub. Select **the existing `smoke_balanced_01`**, click `Start selected` (no need to recreate). It previously failed before creating checkpoints.
6. Check **View selected C++ log** for `[Research Hub] PPO samples/iteration=4096 minibatch=2048` and increasing `Total Timesteps`. After a couple of iterations use **Request safe save + stop**.

## Safety details

- The fix aligns any requested integer batch size *down* to the nearest positive minibatch multiple. 5000 becomes 4096 and 2048 stays 2048. For requested sizes below 2048, the minibatch equals the requested batch.
- The trainer's C++ source changes require a rebuild. Editing Python settings alone cannot fix the currently compiled binary.
- No `.lt` or `.pt` file is modified. This patch does not start or stop a trainer or delete experiments.
- If you already modified the exact minibatch assignment, the patch refuses to guess. Send us the output and we can adapt it.
- Existing smoke experiment settings may still contain `steps_per_iter: 5000`; the C++ fix handles those automatically.
- After the fix, the next error, if any, must be addressed independently. This has not been tested in your Windows runtime yet.
