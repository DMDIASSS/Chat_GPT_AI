# Research Hub: Rename, Delete (Trash), Restore

Compatible with the GigaLearn Research Hub v1 GUI (including the Encoding, PPO Batch, and Defense 1v1 hotfixes).

## Install

1. **Close the Research Hub** and make sure no training runs are active.
2. Extract this ZIP directly into `E:\Downloads\Chat_GPT_AI`. It creates three new files in `GigaLearn_Project\Research_Hub` and does **not** replace `hub_core.py`, `hub_cpp_patch.py`, or your experiments.
3. Double-click `GigaLearn_Project\Research_Hub\ADD_EXPERIMENT_MANAGEMENT.bat`.
4. Wait for `SUCCESS`, then reopen Research Hub.

The installer modifies **only** the existing `hub_app.py` after checking for known source anchors. Before replacing, it saves a timestamped copy `hub_app.py.before_experiment_management_*.bak`. If your app is a different version, the installer refuses to modify it.

## Controls (Experiments tab)

- **Rename selected:** Select an experiment, enter a new name, and confirm. The entire folder and saved `.lt` checkpoints are moved together. No training weights change. The destination name must not already exist. Paths in external scripts / old tournament schedules will still reference the old name.
- **Delete selected:** Select an experiment and confirm twice (including typing its exact name). This moves the complete directory, **including checkpoints and optimizer state**, to `Research_Hub\experiment_trash\...`. It does **not** permanently delete data.
- **Restore from Trash:** Choose a numbered archived experiment and confirm. Restores it to `Research_Hub\experiments\<name>` if that name is free.

Rename and Delete refuse running experiments and pending safe-stop requests. Finish **Request safe save + stop**, wait for the process to exit, then refresh before managing it. No C++ rebuild is necessary. Do not manually manipulate any `launch.lock` or `running.json` files while a job is active.

## Known limitations

- There is no **permanent wipe** button; remove entries from `experiment_trash` manually only when you're certain you no longer need them.
- Renaming a parent experiment can leave stale **display-only lineage paths** in existing child metadata (the children's seed weights remain copied, so they are unaffected).
- Any hand-maintained tournament results or Windows shortcuts that refer to an old experiment name must be updated yourself.
- The GUI shows only the 20 most recent Trash entries for Restore; older entries remain accessible on disk.

These management controls do not evaluate performance and do not change the compatibility between GigaLearn checkpoints and Nexto `.pt` checkpoints.
