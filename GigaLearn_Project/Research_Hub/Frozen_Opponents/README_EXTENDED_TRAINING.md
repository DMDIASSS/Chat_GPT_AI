# GigaLearn tri-teacher challenger: ~1M steps, checkpoint-safe

**Purpose:** substantial but still experimental 1v1 PPO training *against* real frozen
Nexto, Cycle 9 and Wavedash policies. **It does NOT prove a stronger bot will result.**
You already verified the isolated Python teacher and completed three short opponent
smoke tests; this update uses those same compiled training components.

## Install and start (one double-click)

1. Stop any running GigaLearn/Research Hub experiment and backup
   `E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\experiments`.
2. Extract this ZIP directly into `E:\Downloads\Chat_GPT_AI` (merge folders; **do not delete the project**).
3. In `GigaLearn_Project\Research_Hub\Frozen_Opponents`, double-click **`1_START_TRAIN_1M.bat`**.
   It installs a **Python-only** save-interval patch and launches training. **No C++ rebuild**.
4. Keep the terminal open. It will train and save automatically. See `3_CHECK_STATUS.bat`
   *after* completing or from another terminal to check completed rounds.
5. If you need to stop midway, double-click **`4_SAFE_STOP_AFTER_PPO.bat`** in another window.
   The C++ trainer saves on the next PPO boundary. Rerun `1_START_TRAIN_1M.bat`
   later to continue without erasing saved checkpoints.
6. When 5 rounds finish, `2_CONTINUE_TRAIN_3M.bat` extends the **same** challenger
   to 15 rounds total (~2.95 million student steps). **Do not run both at once.**
7. Use the installed GigaLearn RocketSim Watch tool to watch
   `tri_teacher_challenger_01` vs previous GigaLearn models; optionally run
   `5_READ_ONLY_EVAL.bat` for a small read-only first-goal tournament.

## Actual training schedule

- Reads the **latest** nonzero checkpoint from `nexto_rotation_01` exactly once.
- Creates a completely separate `tri_teacher_challenger_01` experiment via the
  existing `frozen_cli.create` checkpoint-copy routine.
- Each round: ~65,536 student PPO samples against **Nexto**, ~65,536 against
  **Cycle 9**, ~65,536 against **Wavedash**. The C++ teacher rotation is based
  on PPO boundaries, so exact numbers may overshoot slightly.
- **5 rounds = at least 983,040 student PPO timesteps**, spanning all three
  teachers five times. Another **10** rounds extends to ~2.95M.
- Checkpoints are automatically saved approximately every **32,768 steps**,
  and at the end of every bounded round; unlike the prior 4,096-step setting,
  this avoids creating hundreds of redundant checkpoints. No pruning/deletion.
- The experiment receives a different deterministic arena RNG seed each round
  to reduce exact-start repetition; the teacher rotation and team swap are
  handled by the compiled bridge.
- Inference is isolated in an external Python 3.11 process so the C++ CUDA and
  Python Torch DLLs are not initialized in the same process.
- Existing checkpoints Cycle 9, Wavedash, replay/TAS, `nexto_rotation_01`,
  Balanced and Shooting/Defense **are not updated or deleted**.

**This is opponent PPO, not Nexto behavior-cloning/DAgger.** The policy receives
its own simulated rewards while competing with frozen opponents; the teachers
are not updated. Training against good players will not automatically transfer
mechanics or make the student competitive, particularly if its basic ball control
is still weak. Treat it as an experiment and evaluate actual gameplay afterward.

## Runtime and disk

The earlier test delivered around 477 **student** steps/s with Python teacher
inference. At that *non-guaranteed* rate, 983,040 steps would take roughly
35 minutes plus loading and checkpoint overhead. Full 3M steps might take ~2 hours.
Space: checkpoints are not deleted; keep sufficient free disk space.

## Reports and controls

Experiment folder:

`GigaLearn_Project\Research_Hub\experiments\tri_teacher_challenger_01`

- `checkpoints\<step>\` — saved native GigaLearn .lt weights + statistics
- `extended_rotation_state.json` — stage journal and teacher count assertions
- `reports\frozen_ppo.log` — actual C++ trainer logs
- `reports\extended_rotation.log` — step orchestration logs and errors
- `extended_rotation.lock` — refuses to start duplicate controller processes
- `request_safe_stop.flag` — consumed by trainer on next safe PPO boundary

If power cuts out or you terminate the terminal forcefully, it may leave an
`extended_rotation.lock`. **Do not delete it blindly**. First verify in Task
Manager there is no `GigaLearnBot.exe` or active extended launcher and no
`launch.lock` in the experiment. Only then manually clear the stale lock and
resume. The stage journal never claims a completed round before auditing it.

The launcher verifies every completed round contains native PPO cycle messages
for **each** teacher and that new student checkpoints advance. It marks errors
instead of saying SUCCESS when the C++ process reported a fatal error. A
completed round is **not a skill promotion**. `5_READ_ONLY_EVAL.bat` compares
GigaLearn `.lt` candidates against each other, **not** against Nexto-family
actors; a proper frozen-teacher match evaluation remains future work.

## Compatibility

Requires your **already working** bridge:
- DLL Guard Fix (`FROZEN_DLL_BUILD_GUARD_V1`),
- Isolated Python Worker Fix (`FROZEN_WORKER_SUBPROCESS_V1`),
- 1v1 teacher smoke tests completed, new checkpoint > 0,
- `GigaLearnBot.exe` / `GigaLearnCPP.dll` built and working,
- registered Python 3.11 (`py -3.11`).

The installer modifies **only** `Frozen_Opponents\frozen_cli.py` to add
`--save-every` and `--seed` arguments and checks exact source anchors. It backs
up the original to `frozen_cli.py.before_extended_rotation_v1.bak` and is
idempotent; if your source is different, it refuses to patch. This is a Python
update, not a compiler change. Never overwrite original Cycle 9 or Wavedash.
