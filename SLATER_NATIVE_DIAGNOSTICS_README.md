# Watch and measure native policies

GigaLearn supplies fast native rollout/optimization; it does not make the training objective sample-efficient or transfer update180's attention weights into an incompatible native MLP. Update180 began with an already capable Nexto policy. The native campaigns began with a weak native model. Speed and training time are not evidence of strength.

The supplied logs identify the gap: campaign 14 mastered touch warmup but failed 32/32 ground scoring cases. Campaign 15 improved teacher KL from 2.90 to 1.09 yet scored zero in its first eight match screens, conceding 48 versus the starting checkpoint's 32. That is better teacher fit on that bank, not demonstrated game improvement. KL values from different collected banks are not directly comparable.

## Inspect now, without stopping training

Extract `Slater_Native_Diagnostics_Update.zip` into `E:\Downloads\Chat_GPT_AI`. This ZIP adds tools and does not replace the existing trainer/backend. It contains no models or replays.

- `NATIVE_16_ANALYZE_AND_WATCH.bat`: takes a verified private snapshot of the latest completed model recorded by campaign 15, or campaign 14 when no 15 status exists. It compares greedy student, sampled student and greedy update180 on the same starts/seeds/colors, then opens `WATCH.html` in a browser. No RLBot export or native rebuild is required. Existing training can continue; CPU contention may reduce its speed while inspection runs.
- `NATIVE_19_CHECK_HUMAN_IMITATION.bat`: quick read-only comparison on the existing event bank's validation labels plus cached raw-control coverage. No re-parsing.
- `NATIVE_19_AUDIT_REPLAY_INPUTS.bat`: additionally parses a deterministic sample of 12 raw `.replay` files and examines the original parser tables before conversion. Persistent audit parsing is cached by replay SHA. Parsing can take several minutes. Use `--raw-count 212` for a longer full audit when desired.

Inspection reports: `data\isolated\native_inspection\inspect_*\WATCH.html` and `report.json`. Input/label reports: `data\isolated\replay_input_audits\audit_*\INPUTS.json`. These reports contain no secret/API token. The tools preserve source checkpoints and snapshots; they fail if a checkpoint changes during copying rather than mixing partially written weights.

To inspect a specific checkpoint, give the entire numbered directory, not a single POLICY.lt:

```bat
.venv\Scripts\python.exe -u slater_native_inspect.py analyze --checkpoint "E:\Downloads\Chat_GPT_AI\data\isolated\gigalearn_native\runs\YOUR_RUN\checkpoints\YOUR_NUMBER" --open
```

The HTML player has case selection, timeline scrubbing, play/pause, speed controls, team colors, car headings, ball height and controller values. It replays actual simulated states. Metrics separate motion, touches, goalward touches, geometric shot proxies, goals/concessions, boost use, and positioning behind/ahead of the ball. A moving bot is not counted as a scorer. The `match` task keeps learner kickoff script OFF; `match_scripted` turns it ON as an explicitly separate diagnostic. Rivals use scripted kickoff in both. This detects a kickoff deficit without hiding the policy's unscripted performance.

Open-goal tests are close shots with a parked rival; ground_score tests use the installed curriculum's current setup (whose source SHA is recorded). Full-match tests include normal kickoff resets and active opponents. Short matched screens are exploratory; they do not independently certify a best model or competitive rank. Python RocketSim may differ from the C++ training simulator version.

## RLViser 3D viewing

1. Download and open the Windows RLViser application from https://github.com/VirxEC/rlviser/releases/latest.
2. Run `NATIVE_17_INSTALL_RLVISER.bat` once to install only `rlviser-py==0.6.14` into the existing venv. It does not reinstall Torch/RocketSim.
3. Keep RLViser open and run `NATIVE_17_WATCH_RLVISER.bat` for two minutes of raw-policy play against update180 with scripted rival kickoff. This is a private model snapshot, not an export.

For scripted learner kickoff or a close-shot case:

```bat
.venv\Scripts\python.exe -u slater_native_inspect.py watch --task match_scripted --seconds 120
.venv\Scripts\python.exe -u slater_native_inspect.py watch --task open_goal --seconds 12
```

Cloud validation imported RLViserRenderer, converted actual RocketSim car states and sent a render packet. The cloud has no viewer executable/GUI; seeing the 3D window is a local check. If the client prints a failed auto-launch message, start the desktop application yourself. The browser replay works without RLViser.

## Are replay inputs genuine, and is the student imitating them?

`INPUTS.json` distinguishes recorded throttle/steer evidence from converter processing: interpolation, smoothing and filling. It reports nonmissing fractions, unique values and invalid ranges, without replacing missing raw controls with zeros. Raw jump/boost activity flags are evidence of replicated state, not a complete original button stream. The installed rlgym-tools converter infers pitch/yaw/roll from angular dynamics; it overwrites those axes with inverse-control estimates. Aerial controls are therefore approximate labels, not verified original human stick inputs.

Validation uses only split 1 rows, never the untouched test split. Current and original-native models get exactly the same sampled validation rows and feasible action masks. Reports include confidence-weighted cross entropy, idle choices and label probability mass on the student's chosen action. Improvement means better agreement with reconstructed labels, not proof that the model understands human intent or reproduces a move successfully. A cached source coverage count only proves that some recorded control fields were present; the optional raw audit provides finer evidence. Physical replay-window verification and actual goals remain necessary.

`training_provenance` also counts actual `SLATER_REPLAY_BC` and `SLATER_TEACHER_BC` optimization epochs in the current native run's logs. Campaign 15 skips repeating the inherited human warmup; its printed human-fit score is a measurement, not evidence of active human-label optimization. Its current optimization is frozen-teacher imitation plus native PPO rewards. The scoring experiment similarly focuses on teacher/goal training; neither silently claims ongoing human-replay training.

Send `report.json` (or a ZIP if large), `INPUTS.json`, and scoring experiment `ranking.json`/`games.json` for diagnosis. The earlier 92 MB bank can be compressed as ZIP for transfer; it was not fully inspected in cloud.
