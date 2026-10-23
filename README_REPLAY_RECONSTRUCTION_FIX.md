# Replay reconstruction v3: verified on the supplied original replay

This source update fixes zero-chunk reconstruction in the fresh replay imitation
pipeline. The uploaded progress report had 33 failed replays and zero samples.
That job had not begun training. W&B authentication is unrelated to parsing.

## Install into your existing project

1. Run `REPLAY_IL_PAUSE.bat` with your previous dataset/run arguments, if any.
2. Wait for the **original working CMD** to finish pausing. The pause script's
   own completion only confirms it sent the request.
3. Extract this ZIP into `E:\Downloads\Chat_GPT_AI`, allowing included source
   files to replace the old versions. Keep `data`, `.venv` and existing models.
4. For the incomplete, untrained dataset shown in the log, run
   `REPLAY_IL_START.bat` again with the previous dataset/run settings.
5. Confirm CMD prints **`RECONSTRUCTION v3: RocketSim interpolation`** and that
   `saved chunks` / `samples` become positive before leaving a full run active.

Outdated shards rebuild because the reconstruction configuration changed. Raw
replays remain saved. Pause downloads during preparation: adding files can change
its sampling budget when preparation is restarted.

If a dataset or training run has already completed since that log, use a new
configuration-compatible experiment instead of modifying its saved protocol:

```bat
REPLAY_IL_START.bat --dataset data\isolated\replay_imitation\dataset_reconstruction03 --run replay_reconstruction03
```

Request pause for that custom experiment with:

```bat
REPLAY_IL_PAUSE.bat --dataset data\isolated\replay_imitation\dataset_reconstruction03 --run replay_reconstruction03
```

## What changed

The preceding update enabled RocketSim interpolation, which fixed repeated car
poses and internal contact/jump/flip/boost state not advancing. The original
replay now reveals two further causes of zero chunks:

* Car physics updates in this replay are commonly about 67-100 ms apart. The
  50 ms cutoff repeatedly discarded partially assembled chunks. Interpolation
  is now bounded to **16 physics ticks (133 ms)** at both transition endpoints.
  Every accepted 32-tick chunk must also include an **observed replay refresh
  for every car**. Unobserved predictions cannot validate their own labels.
* The validator treated the spherical ball's surface orientation like a car's
  orientation. Surface orientation does not change sphere collision geometry
  or appear in the model observations. Rotation comparison now applies to cars.
  Ball spin remains in the simulator; ball and car positions/linear velocities
  and all car orientations still have to fit.

Position (40 uu), velocity (180 uu/s), and car rotation (0.3 matrix-norm) limits
remain unchanged for transitions and full chunks. Long gaps, malformed controls,
nonfinite or invalid states, missing observations and failed full chunks remain
rejected. No missing chunks or demonstration states are fabricated. These are
reconstructed inputs, not exact recovery of human hardware inputs.

Rejection reasons print in CMD. `parse_progress.json` retains reconstruction
counts even when a replay produces no usable examples. Dataset configuration
records the interpolation bound, car-only rotation check and refresh requirement.

## Verification and limits

The supplied original `.replay` was parsed with Carball and RLGym Tools 2.6.5.
It produced 10,639 converted gameplay frames. The preceding importer produced
**zero examples**. This correction produced **1,024 saved examples** (the
per-replay reservoir cap), with **611 complete two-car chunks verified** and
**295 complete chunks rejected**. Each verified joint chunk supplies one example
per player before sampling. The single replay did not yield a verified kickoff.

Automated tests cover sparse updates, excessive staleness, missing observed
refreshes, irrelevant ball orientation, meaningful car rotation, invalid motion,
causal observation histories, and supervised save/resume. An opt-in integration
test parses the private original replay and checks the cached shard's finite
values, shapes, binary buttons, identity and split guards. The raw replay is not
included or published. To run that check locally:

```bat
set "REPLAY_IL_REAL_REPLAY=E:\Downloads\Chat_GPT_AI\data\replays\ranked-duels\098357fd-596c-4349-98d6-9c7a4117ccc6.replay"
.venv\Scripts\python.exe -m pytest -q tests\test_replay_imitation.py tests\test_replay_interpolation.py
```

This verifies usable samples from **one original match**. It does not establish
yield for all remaining files, training completion, playing strength or faithful
TAS training. Training still requires two real matches per split; copies of this
one replay are not used to bypass that guard. If another replay yields zero,
share its progress report and original file before running many more failures.
