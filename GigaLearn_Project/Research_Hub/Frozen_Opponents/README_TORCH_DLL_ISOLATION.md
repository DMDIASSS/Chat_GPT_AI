# Frozen Nexto CPU Worker — DLL Isolation Hotfix

## Why

GigaLearn CPP uses C++ LibTorch/CUDA inside its main executable. Importing Python `torch`
inside that **same** Windows process failed with `WinError 1114` loading `c10_cuda.dll`.
The previous trainer printed SUCCESS even though no PPO iteration completed and only
`checkpoints/0` existed. That is *not* a successful training cycle.

## Fix

This update makes the **frozen teacher run in an independent Python 3.11 process**.
The C++ host sees a lightweight Python/NumPy proxy that sends state batches through
stdin/stdout JSON lines and receives 90-action indices. Importantly, Python torch is
loaded **only in the independent process**. GigaLearn student CUDA stays in the main process.

- `install_isolated_teacher.py` preserves your existing `frozen_nexto_bridge.py` as both a
  backup and `frozen_nexto_worker_core.py`, swaps in the subprocess proxy, and patches
  `frozen_cli.py` with explicit Python interpreter and stricter fatal-error checks.
- No C++ files are modified; **no C++ rebuild is needed**.
- No checkpoints, weights, original Nexto, Cycle 9 or Wavedash models are modified.
- On success, `teacher_worker_stderr.log` appears under `Frozen_Opponents/reports`.
- This uses CPU teacher inference; it will be slower than native C++ self-play.

## Steps

1. Close any active training. Extract ZIP into `E:\Downloads\Chat_GPT_AI` (merge existing folders).
2. Run `GigaLearn_Project\Research_Hub\Frozen_Opponents\FIX_TORCH_DLL_ISOLATION.bat`.
3. In CMD run:

   ```bat
   cd /d "E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Frozen_Opponents"
   0_PREFLIGHT.bat
   ```

4. When all three teachers pass, run `4_SMOKE_NEXTO.bat` (do **not** re-run `3_CREATE_BRANCH.bat`;
   the existing `nexto_rotation_01` checkpoint folder should still contain checkpoint `0`).
5. Confirm `[FrozenNexto] ISOLATED PYTHON WORKER ACTIVE`, `FROZEN teacher inference ACTIVE`,
   PPO update and a *new* numbered checkpoint larger than `0` before attempting Cycle 9/Wavedash.

If there is another error, send both the terminal output and
`Frozen_Opponents\reports\teacher_worker_stderr.log` and
`Research_Hub\experiments\nexto_rotation_01\reports\frozen_ppo.log`.

## Recovery

The installer creates `.before_worker_isolation_v1.bak` files for the original module and
CLI. Restore them if needed. Installing twice is safe. A DLL init error without a newer
checkpoint must **not** be reported as success.

## Remaining caveat

This fix addresses only a DLL collision and false-success reporting. It does not by itself
prove the RocketSim-to-Nexto observation semantics, competitive improvement, or the accuracy
of any game result. Validate the first real training cycle in RocketSim before long training.
