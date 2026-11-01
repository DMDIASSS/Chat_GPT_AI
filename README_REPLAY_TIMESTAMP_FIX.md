# Replay preparation timestamp fix

The uploaded TAS audit completed normally. It audits files and does not train a
model. The uploaded checkpoint comparison is also progressing through real
1v1/2v2/3v3 games; its partial log does not show a completed overall comparison.

The training importer has a separate issue. The supplied progress report shows
21 replays processed, 20 rejected with no usable action chunks, and only 16
saved examples. Those files do not demonstrate successful model training.

RLGym Tools 2.6.5 supplies `tick_count = replay_seconds * 120`, a floating-point
timestamp. The importer previously truncated timestamp differences and sampled
on a grid derived from unnormalized floats. Tiny timestamp jitter could turn
four physics ticks into three and invalidate long action chunks.

This update rounds absolute frame times to the nearest physics tick before
differencing and sampling. It copies frames rather than modifying source data.
Position, velocity, rotation and full-chunk validation limits remain identical.
An executable RocketSim regression reproduced the defect: the same motion gave
54 usable examples with integer times and only two with fractional jitter. The
fixed importer produces all 54, with identical histories and controls.

Stop the old importer with Ctrl+C, extract the update into
**E:\Downloads\Chat_GPT_AI**, then run **REPLAY_IL_START.bat** again. Raw replays
are preserved. The importer code fingerprint forces outdated shards to be
reconstructed rather than silently reusing their old preparation configuration.
This update is intended for the incomplete dataset shown in your report. If a
dataset/run has already finished since that report, use a fresh dataset and run:

```bat
REPLAY_IL_START.bat --dataset data\isolated\replay_imitation\dataset_timefix02 --run replay_timefix02
```

The uploaded `.npz` has 16 finite, correctly shaped examples, and its kickoff
book is empty. It contains no original replay motion needed to measure whether
this timing fix resolves the other rejected files. One original failing
`.replay`, such as `04a9bc57-c52f-44bf-9db1-bc8d5fc6c612.replay`, is still needed
for verification against the user's actual game recording. No real-data yield
or competitive improvement is claimed from this synthetic regression.
