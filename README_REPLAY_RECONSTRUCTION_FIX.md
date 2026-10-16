# Replay reconstruction update

The uploaded log processed 30 of 279 replays with 30 failures and zero samples.
That job had not reached training; W&B authentication is unrelated to these
reconstruction failures. The log alone does not identify every failure cause.

The importer incorrectly selected the replay converter's `none` interpolation
mode. Replay car updates can repeat across frames. That mode keeps repeated
poses frozen and does not advance internal contact, jump, flip and boost state
between observations. Comparing those states to a moving simulation can reject
otherwise consistent motion.

This update selects the converter's supported `rocketsim` interpolation. It
predicts between updates and reapplies observed replay physics on new updates.
Timestamp normalization, stale-state rejection, and all position, velocity,
rotation and complete action-chunk checks remain enabled with the same limits.
Rejection reasons now print in CMD, and reconstruction counts remain in
`parse_progress.json` even when a replay produces zero usable chunks.

## Install into the existing project

1. Run `REPLAY_IL_PAUSE.bat`. If the active job used custom `--dataset` or
   `--run` arguments, pass those same arguments to the pause script.
2. Wait for the **original working CMD** to finish pausing. The pause script's
   own completion message only confirms that it sent the request.
3. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`, allowing its source files
   to replace the old versions. Do not remove `data`, `.venv` or your models.
4. For the incomplete, untrained dataset shown in the uploaded log, run
   `REPLAY_IL_START.bat` again using its previous dataset/run settings.
5. Confirm CMD prints:

   `RECONSTRUCTION: RocketSim interpolation; transition and full-chunk quality checks enabled`

Preparation rebuilds outdated shards because its reconstruction configuration
changed. It keeps raw replays. Pause downloads during preparation to avoid
changes to the per-replay sampling budget on later starts.

If you have already completed a dataset or begun training since that log, the
source fingerprint has changed, so use a new dataset and training run instead:

```bat
REPLAY_IL_START.bat --dataset data\isolated\replay_imitation\dataset_reconstruction03 --run replay_reconstruction03
```

For that custom run, request pause with:

```bat
REPLAY_IL_PAUSE.bat --dataset data\isolated\replay_imitation\dataset_reconstruction03 --run replay_reconstruction03
```

## Validation and limits

A RocketSim-generated replay-converter fixture with repeated car updates
reproduced **zero** usable chunks in `none` mode and **54** with this correction,
without changing quality limits. This is a regression test, not professional
replay training data. Invalid motion is still rejected, and failed-replay
diagnostics are tested. The user's original failing `.replay` files were not
available here, so their actual usable sample yield remains unverified.

If samples stay at zero, stop the job and share `parse_progress.json` plus one
original failing `.replay`. Do not spend another full parsing pass guessing.
