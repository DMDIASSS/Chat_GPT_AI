# Frozen Nexto → Cycle 9 → Wavedash bridge — research build

## What this is

This is an **experimental 1v1 student-only PPO training integration**, not an automatic skill-improvement guarantee. It uses the **actual original Nexto TorchScript actor and the actor state dictionaries from your native Cycle 9 and Wavedash `.pt` checkpoints**. Native Nexto policies are frozen; **only the GigaLearn `.lt` student receives PPO gradient updates**. Unlike a training schedule without an opponent, the embedded Python model actively chooses an action for the opposite team at every RocketSim decision.

Your previous `replay_tas_link_01` model remains untouched. Each `.pt` teacher remains read-only, and the new branch writes only under `Research_Hub/experiments/nexto_rotation_01`.

**Important limitation:** Python-side model inference was tested, and 1v1 source/patching tests passed. This custom C++ patch **has not yet been compiled or run in MSVC on your Windows PC**. Perform one tiny smoke cycle first, and inspect the training log before making any competitive claims.

## Installation and first safe run

1. Stop training, close both Hub GUIs, and make your usual folder backup.
2. Extract the ZIP into `E:\Downloads\Chat_GPT_AI` (merge folders; don't replace the entire existing project).
3. Run `0_PREFLIGHT.bat`. It loads three native teachers without training, validates action-table/model compatibility. If paths differ from the defaults, run `py -3.11 frozen_cli.py preflight --nexto "..." --cycle9 "..." --wavedash "..."`.
4. Run `1_INSTALL.bat`. It patches only **Learner.cpp** and adds the new FrozenNextoBridge.h. `Learner.cpp.before_frozen_nexto_bridge_v1.bak` is the backup. No other original project source is overwritten.
5. Open **x64 Native Tools Command Prompt for VS 2022**. Run:

   ```bat
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Frozen_Opponents
   2_BUILD.bat
   ```

6. Run `3_CREATE_BRANCH.bat` (copies replay+TAS linked checkpoint; never moves/deletes it). If it cannot locate the seed, pass your exact `.lt` checkpoint directory using `py -3.11 frozen_cli.py create --seed "FULL_PATH_TO_CHECKPOINT" --name nexto_rotation_01`.
7. Run `4_SMOKE_NEXTO.bat` **only after successful compilation**. This does ONE bounded PPO learning test against frozen Nexto, saving a new checkpoint. It may take longer than your all-C++ self-play because teacher inference uses CPU/Python.
8. If the log reports real frozen Nexto actions, a new checkpoint is saved, and smoke evaluation is sane, run `5_SMOKE_CYCLE9_WAVEDASH.bat` to resume against Cycle 9 and Wavedash.

**Always check the real log** `Research_Hub\experiments\nexto_rotation_01\reports\frozen_ppo.log`. Expect lines like `[FrozenNexto] teacher rotation -> cycle9` and `[FrozenNexto] PPO cycle ... teacher=cycle9`.

## Stop and recover

While running, create the empty file `Research_Hub\experiments\nexto_rotation_01\request_safe_stop.flag`. The Research Hub trainer saves after the current PPO update and exits safely. Avoid Ctrl+C unless the trainer is unresponsive.

If the new source fails to compile, you can restore `Learner.cpp` from `Learner.cpp.before_frozen_nexto_bridge_v1.bak` and rebuild. This will not affect checkpoints.

If there is any model architecture or action-table mismatch, **training aborts**. The bridge does not silently replace a teacher with a random opponent.

## How the bridge works

- GigaLearn PPO collects rollouts for **one student car per arena**.
- A Python object uses Nexto's original 37×24 entity observation format (from `nexto_obs.py`) and its original 90 controls. RocketSim C++ passes boost pads, ball state, positions, velocity, orientation, flip/ground/boost status; previous teacher actions are tracked across steps and reset at episode boundaries.
- The original Nexto TorchScript policy is instantiated separately for all three teachers. Cycle 9/Wavedash actors load the checkpoint `actor` state dictionaries with `strict=True`. Only the chosen teacher's actor performs forward inference, with `torch.inference_mode()`.
- The teacher runs on CPU (recommended for GTX 1650 4GB); the student PPO can use CUDA. The code requires exact matching discrete action tables.
- The student gets rewards for its own GigaLearn actions and alone enters the experience buffer. PPO never trains the frozen actor.
- Teacher **rotation occurs at PPO iteration boundaries**, based on accumulated student timesteps. Teacher side also alternates per iteration. Initial smoke uses 4096 intended steps per teacher. The physical number of actual steps in one iteration may slightly exceed 4096 due episode truncation, so verify actual teacher order in the log.

## Scientific limitations

- This is the policy-only Nexto actor; **Nexto's RLBot scripted kickoff is not reproduced**.
- Precise Nexto observations were ported from the existing RLGym v2 bridge, but the C++ physics-to-Nexto coordinate mapping **requires validation with live RocketSim states**. A packet sanity check fails on invalid rotation bases.
- These are RocketSim PPO training steps, not demonstrations/DAgger, and no competitive claim follows from more training steps.
- The models are under Nexto/Necto **CC BY-NC-SA 4.0**; review licensing before any commercial use. See `NEXTO_LICENSE.txt` and the bundled observation builder's header.
- Use your Gameplay Eval and RLViser to judge touches, shots, positioning and goals. Never automatically promote on training reward or replay label accuracy.

## Python 3.11 and `.venv` notes

The runner sets `GL_FROZEN_SITE_PACKAGES` to `E:\Downloads\Chat_GPT_AI\.venv\Lib\site-packages` so the **embedded** Python 3.11 process can import `torch`/`numpy` from the same project environment used to build GigaLearn C++. It also makes PyTorch's `torch\lib` DLL directory available on Windows. The launch scripts use `py -3.11` and will fail safely if Python 3.11 isn't registered. Do not rebuild the project's Python environment just for this add-on.
