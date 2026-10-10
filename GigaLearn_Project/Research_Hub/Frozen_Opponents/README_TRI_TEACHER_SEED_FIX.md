# Tri-Teacher 1M — duplicate `--seed` fix

### What failed

`ERROR: argument --seed: conflicting option string: --seed` occurred because frozen_cli.py already used `--seed PATH` to specify a GigaLearn seed checkpoint in its `create` command. The v1 extended rotation patch added another parser option `--seed INTEGER` for training. `argparse` refused to initialize, so the 1M trainer never started. A round-1 failure entry exists in the challenger journal, but completed_rounds remains 0 and checkpoint 0 remains untrained.

### Install and resume

1. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`, merging folders.
2. Double-click `GigaLearn_Project\Research_Hub\Frozen_Opponents\FIX_TRI_TEACHER_SEED.bat`.
3. Confirm it prints `PASS: frozen_cli.py run parser loads without option conflicts.`
4. Double-click the EXISTING `1_START_TRAIN_1M.bat` again.
5. The same `tri_teacher_challenger_01` branch will restart from checkpoint 0. **Do not** delete or recreate that branch.

### Technical change

- `frozen_cli.py`: original `--seed PATH` retained for checkpoint creation; new `--run-seed INTEGER` for random simulation seeds; run() validates/uses `args.run_seed`.
- `extended_rotation.py`: calls `frozen_cli.py run` with `--run-seed`.
- `extended_frozen_cli_patch.py`: future fresh installations use the non-conflicting name.

The installer preserves backups next to the 3 modified Python scripts. It refuses unexpected versions and does not modify teacher weights, GigaLearn model checkpoints, C++ code, CUDA or PyTorch packages. No C++ rebuild is necessary.

**Expected:** During round 1 you should see Nexto/Cycle 9/Wavedash PPO cycle logs and a checkpoint above 0. This is experimental training, not guaranteed gameplay improvement. If you see any other ERROR, stop and send the full traceback or extended_rotation.log.
