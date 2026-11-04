# NovaForge v1.0.1 — Windows checkpoint saving

Fixes `OSError: [Errno 9] Bad file descriptor` during `1_CHECK.bat` in `save_ppo`.

The v1.0 saver reopened completed temporary model files with `rb` and called `os.fsync`. Windows requires a writable file descriptor for this flush. Both full PPO checkpoints and TorchScript actor exports now use the same helper, reopening with `r+b`, flushing, syncing and closing before atomically replacing the destination. `r+b` preserves the serializer's bytes. Sync errors still propagate; the fix does not suppress disk failures or skip the durability step.

JSON metadata and demonstration datasets already use writable handles; they were checked as part of this fix. Policy architecture, model contracts and checkpoint formats are unchanged.

## Apply the update

1. Close NovaForge checks/training processes.
2. Extract `NovaForge-v1.0.1.zip` into your existing `Chat_GPT_AI` folder. Allow replacement of the NovaForge source files. Extract into the parent so the result remains `Chat_GPT_AI\NovaForge\run.py`, without a second nested NovaForge folder.
3. Keep your existing `NovaForge\.venv`, `assets`, datasets, models and runs. Those folders are excluded from this ZIP. No dependency reinstall is required.
4. Double-click `NovaForge\1_CHECK.bat` again. Before trainers are downloaded, the expected test result is **19 passed, 5 skipped**, followed by `DOCTOR_PASS` and `CHECK_PASS`.
5. Run `2_SMOKE.bat`. It checks actual PPO checkpoint/resume and frozen-actor export. Continue with `3_FETCH_TRAINERS.bat` after `SMOKE_PASS`.

The skipped tests are the optional Nexto/Ripple tests; `3_FETCH_TRAINERS.bat` downloads the required assets and runs them.

## Validation

Two regression cases enforce Windows' writable-descriptor requirement during real checkpoint and actor serialization, including on Linux. Both reproduced `Errno 9` with the original implementation and pass with the fix. Loading the resulting artifacts preserves policy actions.

The complete teacher-enabled suite passes **24 tests**. The core archive passes **19 tests with 5 optional teacher tests skipped**. A two-worker real PPO smoke, checkpoint restore, 128 additional decisions and frozen-actor parity pass in Linux. Native Windows execution of this hotfix still needs the user's rerun; the writable-descriptor behavior is simulated in the Linux regression cases.
