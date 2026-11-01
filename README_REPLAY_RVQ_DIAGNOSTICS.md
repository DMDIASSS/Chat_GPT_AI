# Diagnose stationary behavior, own goals and missing jumps

This update adds evidence collection to the existing **ReplayRVQ01** runtime.
It does not change trained weights, training fingerprints, parsed chunks,
the action codec, candidate ranking or issued controls. No forced throttle,
jump, boost, recovery script or handmade movement reward is added.

The symptom does not establish that more epochs are needed. Possible causes
include a runtime error, low-drive choices, persistent handbrake, latency,
forecast/value errors, or weak reconstructed jump examples. A bump changing
the behavior is also consistent with a deterministic policy leaving a stationary
state; it is not proof that the process froze.

## Install without training again

Extract this source update into `E:\Downloads\Chat_GPT_AI`, replacing included
files. Preserve `.venv`, all data and existing exports. Then run:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_RVQ.bat export --name ReplayRVQ01_Check
```

Load `data\rlbot_exports\ReplayRVQ01_Check\bot.cfg` in RLBot v4.
Choose another new name if that folder already exists. This re-exports the
validation-selected existing model; **no training or replay parsing is run**.
Copying only `bot.py` into an old export would break its integrity manifest.

After a stationary episode, leave it still for at least five seconds so the
report is written. The export contains:

- `RVQ_DIAGNOSTICS_<car_index>.json`: each bot's own report.
- `RVQ_DIAGNOSTICS.json`: latest writer, retained for compatibility.

The report retains the last stationary episode after movement resumes. It
records exact issued controls, speed, decisions advancing, current and previous
runtime errors, button press/release counts, handbrake, per-candidate values,
search latency and the chosen chunk's executed versus unexecuted controls.
It also keeps a bounded recent trace of car/ball physics and issued controls,
without player names, to help investigate bad touches and own goals.
The logger also runs on a wall-clock interval if the packet clock stops.

Interpretation:

| Evidence | What it distinguishes |
|---|---|
| `runtime_error_active` / `last_runtime_error` | Exception handling returned neutral controls |
| `stationary_with_low_drive_commands`, decisions advancing | Policy/search repeatedly issued little drive; not proof of a stopped inference loop |
| `stationary_with_drive_commands` | Commands were issued but motion stayed low; inspect contact, handbrake, packet/input execution |
| `drive_only_after_executed_prefix` | Motion was deferred past tick eight and never executed before replanning |
| Jump press/release edge counts | Whether jump commands are absent or held rather than released and pressed again |
| Candidate budget and latency | Whether inference is overrunning its control interval |

Stationary play can be intentional; the report never treats every wait as a
failure and never changes an action based on these labels.

For rare jumps and poor decisions, also inspect/send these saved reports:

```text
data\isolated\replay_imitation\rvq_runs\replay_rvq01\codec\selected.json
data\isolated\replay_imitation\rvq_runs\replay_rvq01\codec\button_calibration.json
data\isolated\replay_imitation\rvq_runs\replay_rvq01\policy\selected.json
```

Low codec jump recall indicates a representation/reconstruction issue before
policy learning. Good codec reconstruction with poor greedy-policy jump recall
points to policy selection. Better validation loss does not establish playing
strength. Own goals require actual states/actions to investigate; orientation
tests alone cannot prove the trained value function is accurate.

The provided RocketLM discussion specifies RVQ chunks, a state-only policy,
four-chunk all-car forecasts and endpoint values. We implemented those core
elements. Its private reconstruction details, value calibration and optimized
runtime remain unavailable; the discussion does not guarantee a reproduction
will achieve the author's reported strength.
