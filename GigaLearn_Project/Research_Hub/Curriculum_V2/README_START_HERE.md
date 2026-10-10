# GigaLearn Curriculum Control v1 — replay-first research build

This is a **separate, non-destructive experimental add-on** for your existing `GigaLearn_Project/Research_Hub`. It does **not** silently replace the Research Hub, import Nexto `.pt` into GigaLearn, train on unverified TAS, or promise full multiplayer transfer.

## What currently works / needs checking

| Stage | Current implementation | Trust level |
|---|---|---|
| 1 — Human replays | Parse local raw 1v1 `.replay` files; reconstruct approximate controls using rlgym-tools; convert game states into the native GigaLearn C++ `AdvancedObs`; train isolated `.lt` student using cross-entropy; heldout-by-replay validation | **C++ needs Windows build and runtime smoke test** |
| 2 — TAS | Strict structural audit of `.data` file frames; refuses unverified controller-only imitation | **Audit implemented; training blocked** |
| 3 — Nexto, Cycle9, Wavedash | Records required frozen-opponent adapter; preserves those checkpoints untouched; no pretend gameplay | **Blocked** |
| 4 — Mechanics | Existing Research Hub native `.lt` shooting, defense, power, air, recovery, kickoff profiles; manual evaluation first | **Existing C++ PPO available; improvement not proven** |
| 5 — Multiplayer | Existing GigaLearn 1v2/1v3/2v2/3v3 from compatible seeds, experimental selfplay | **Trainable, but NOT native Nexto opponents; 1v1→multi transfer blocked** |
| 6 — Promotion | Existing paired evaluator and replay validation; no auto-promotion | **Requires better skill diagnostics before any champion update** |

## Install: Windows 10 x64

1. **Back up** `GigaLearn_Project/Research_Hub/experiments`, `GigaLearn_Project/build_py311/checkpoints` and original `data/afk_improved`. Stop training.
2. Extract ZIP into **`E:\Downloads\Chat_GPT_AI`**. Creates `GigaLearn_Project/Research_Hub/Curriculum_V2`. It contains no model data or overwritten existing Hub source.
3. In Curriculum_V2 run `CURRICULUM_0_CHECK.bat`. It detects your existing compiler and raw replay directory.
4. Run `CURRICULUM_1_INSTALL_CPP.bat` (backs up upstream CMake, adds only one C++ BC executable).
5. Open **x64 Native Tools Command Prompt for VS 2022**, then:

   ```cmd
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Curriculum_V2
   CURRICULUM_2_BUILD_CPP.bat
   ```

6. Run `CURRICULUM_3_START_DEBUG.bat`; the GUI opens. Use **1 Extract replay examples** (may take time for hundreds of replays; depends on `rlgym-tools` installed inside the interpreter). Your working `.venv` Python has this library; the standalone Python launcher may not. In that case run the *same script* using your repaired `.venv\Scripts\python.exe`:

   ```cmd
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Curriculum_V2
   "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" curriculum_cli.py extract-replays --input "E:\Downloads\Chat_GPT_AI\data\replays" --output "run_data\my_first_replay_dataset"
   ```

7. Select the generated dataset directory. Click **3 Train replay BC policy** (first use 2–4 epochs). It saves under `results/replay_bc_.../checkpoint/0` and writes a validation report.
8. If the C++ smoke run succeeds, branch into **a new 1v1 Research Hub experiment**, never overwrite `smoke_balanced_01`, `shootingv1` or `defense1v1`:

   ```cmd
   python curriculum_cli.py branch-to-hub --checkpoint "E:\...\Curriculum_V2\results\replay_bc_...\checkpoint\0" --name replay_foundation_01
   ```

9. For PPO, open existing Research Hub, select `replay_foundation_01` and use Start Selected / Request safe save+stop. This is **selfplay with GigaLearn policies**, not Nexto yet. Do not claim it learned from Nexto until the teacher bridge exists.

## Data correctness restrictions

- The replay sample generator accepts only 1v1 two-car states with valid rotations, freshness and legal action approximation; train/validation splits are assigned per **replay filename** (not per frame) to reduce leakage.
- Human replays give only reconstructed controller actions; they may be wrong especially in aerials, demos, flip resets and recovery sequences. Improved validation cross entropy **is not a match win rate**. Human replay labels are not 100% ground truth.
- `native_replay_dataset.npz` from the AFK learner contains native Nexto attention observations (`q/kv/mask`) and **cannot be reused** as GigaLearn `AdvancedObs` directly.
- TAS `.data` captures here have controller frames and no verified per-frame positions/velocities; doing BC from these without alignment would teach nonsensical actions. Audit is the only enabled TAS operation.
- GigaLearn `AdvancedObs` observation size depends on number of players. This package forbids cross-size checkpoint transplantation, including 1v1 to 1v2.
- Compatible Nexto/Cycle9/Wavedash frozen-opponent evaluation and training require a separate adapter that runs native Nexto inference correctly and maps the actions/states. **That adapter is NOT implemented here.**
- Training and metrics produced from this package are experimental. No continuous unattended "run everything" until all guards are satisfied.

## Checkpoint files

C++ behavioral cloning outputs an isolated GigaLearn checkpoint: `POLICY.lt`, `SHARED_HEAD.lt`, `CRITIC.lt`, optimizer files, `RUNNING_STATS.json` (7 files). For a new replay-only policy `total_timesteps=0` intentionally: demonstration training epochs are **not** RocketSim environment steps.

The snapshot conversion does not perfectly reconstruct prior boost-pad timers, prev actions, or flip timers from the recorded replay. These ambiguities weaken imitation. Validation and actual gameplay smoke tests are mandatory. Always preserve `best_verified.pt` and the existing `POLICY.lt` baselines.

## If anything fails

Read the terminal output (or Activity tab). **Do not delete experiments, reinstall CUDA, replace any .lt file, or disable safety protections.** Send the CMake error or the last 100 lines from the replay BC log. There is no guarantee this new C++ target builds on your exact patched version until tried on Windows.
