# Check missing jumps, boost and circling before changing training

Extract the source update into `E:\Downloads\Chat_GPT_AI`, replacing included
files. Preserve `.venv`, datasets, replays, checkpoints and exported weights.

The supplied log shows `ReplayDuelsDoubles` loaded on CPU with no
`REPLAY_MODEL_PAUSED` error. In 76 five-second policy snapshots, jump was false
in all 76 and boost was true once. Token 14 was sampled 22 times; the supplied
matching vocabulary gives it zero throttle and near-full steering. That
explains the observed stopping/circling command but does not prove its cause.

The matching 256-token dictionary has jump presses in the executed first eight
ticks of 50 tokens and boost in 71 tokens. The RLBot wrapper maps both buttons.
Five-second console snapshots can miss short presses, so they cannot establish
that no jump occurred between snapshots. The new counters close this logging gap.

## One check for this exact existing bot

Close RLBot and run:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
CHECK_REPLAY_DUELS_DOUBLES.bat
```

This does two things:

1. Update the `ReplayDuelsDoubles` wrapper and integrity manifest, preserving
   `policy.pt`, `tokens.npy` and the existing scripted-kickoff setting.
2. Compare its actual exported policy against `replay_scratch01\best.pt` on 512
   sampled cached validation examples, on CPU to match the supplied live log.
   It also reports jump/boost/handbrake frequencies in reconstructed targets,
   tokenized targets, and model predictions, separately for first-eight-tick
   controls and the full 32-tick chunks.

It never trains, reparses, starts a match or forces a jump/boost. A mismatched
checkpoint, changed export or failed numerical comparison produces an error.
The report is:

```text
data\isolated\replay_imitation\runs\replay_scratch01\validation_diagnostics.json
```

For a different matching export, use the general commands with its paths:

```bat
REPLAY_IL_FINAL.bat repair --folder data\rlbot_exports\ReplayDuelsDoubles
REPLAY_IL_FINAL.bat analyze --run replay_scratch01 --export-folder data\rlbot_exports\ReplayDuelsDoubles --device cpu --analysis-samples 512
```

## Count actual issued commands and check timing

Restart RLBot and load the same `ReplayDuelsDoubles\bot.cfg`. After a minute of
ordinary play, the export will have written:

```text
data\rlbot_exports\ReplayDuelsDoubles\CONTROL_DIAGNOSTICS.json
```

This contains every wrapper callback's jump/boost/handbrake counts, with learned
policy controls separated from scripted kickoff and neutral output. The
five-second log also prints cumulative counts. Counters restart with the bot.
If several cars use the same export folder, this file contains the latest
writer's separate counters; `car_index` identifies that car, not a merged team.
These are commands issued to RLBot, not proof that a car was able to jump or had
boost available. Physics availability, held-button edges and missed callbacks
can still affect the result in the real game.

Timing fields include last/maximum decision latency, decisions exceeding the
66.7 ms decision budget, maximum packet gap, and gaps exceeding 16 ticks that
reset history. Large gaps can also reflect pauses or debugger stops. CPU in
this RLBot interpreter is separate from CUDA available in the training `.venv`;
changing only `runtime.json` to CUDA cannot install a compatible Torch build.

## Interpret the evidence

| Evidence | What it suggests |
|---|---|
| Export/checkpoint mismatch or failed parity | Resolve the export problem before more training. |
| Very few reconstructed jump/boost targets | Accepted demonstrations or control reconstruction lack that coverage. |
| Reconstructed presses disappear after tokenization | The vocabulary loses those controls; inspect a versioned tokenizer experiment using the raw cached chunks. |
| Tokenized targets contain presses but predictions rarely choose them | The learned policy underpredicts those actions; more elapsed play time does not teach it. |
| Offline predictions are reasonable but live policy rarely issues presses | Investigate live observations, timing and unfamiliar states encountered after its own mistakes. |
| Live commands include presses without the expected movement | Check jump/boost availability, button edges and packet rate in the game. |
| Frequent active-play timing gaps/history resets | Fix deployment latency before attributing everything to training. |

An idle/turning action can feed the policy more unfamiliar states and keep it
stuck. Offline prediction accuracy alone does not guarantee recovery from its
own errors. The current export uses direct policy inference. It does not learn
from deployment games. More training epochs are useful only if validation and
action coverage improve; waiting or training longer alone is not a proven fix.

Share these two generated JSON reports rather than the entire RLBot launcher
log, which may contain unrelated account/launch information. The checks preserve
existing reconstructed chunks, model/optimizer checkpoints and selected weights.
