# Testing and feedback

## What to run

Start with README steps 1–7. Train `duel01` for 10–15 minutes, pause, watch kickoff and open-play clips, then make a report. Resume to one hour if no contract/runtime errors appear. A poor random-start bot is not by itself a code failure; persistent immobility, illegal controls, nonfinite losses or repeated identical unintended behavior need investigation.

Suggested feedback: how often it reaches the ball; misses versus avoids it; chooses backward motion while a turn would work; wastes boost; recovers; can approach from every kickoff geometry; and whether open-play behavior differs from kickoff behavior. Use clips and the recorded inspector, not only reward totals. Please attach the report ZIP. It includes the last two bounded watch recordings, metrics, errors and exact configuration.

## Buttons versus menu

Menu choices: 1 train, 2 pause, 3 kickoff watch, 4 open-play watch, 5 validation, 6 report, 7 export, 8 frame inspector, 9 collection benchmark, 10 fetch Nexto, 11 Nexto watch, 12 Nexto evaluation, 13 separate Nexto training fork, 14 A/B pilot, 15 exact validation pin watch, 16 large confirmation-style panel.

Standalone batch files have their own descriptive filenames; for example `5_REPORT.bat` corresponds to menu 6 and `6_EXPORT_V5.bat` corresponds to menu 7. Use the main menu to avoid number confusion.

## Resource and speed readings

The training `learner transitions/s end-to-end` number includes collection and PPO. Collection benchmark decisions/s excludes PPO. Optimizer examples/s includes repeated epochs. Physics ticks/s counts 120Hz simulation ticks. None of these units should be compared as if identical. W&B is optional; local metrics are the authoritative raw log.

Default memory pause targets: allocated CUDA 2560 MiB, reserved CUDA 3072 MiB, process RSS 8192 MiB. These are admission targets, not measured GTX 1650 peaks. Pause training before playing games. The prototype does not read laptop temperatures or automatically manage thermal limits. A bounded session may slightly exceed its time budget while finishing the current rollout/update or already-running validation.

For a new run you may reduce arenas from 64 to 32 or Torch/native workers from 2 to 1 if the PC lags. Do not change a resumed run's config silently. Benchmark before increasing arenas: a CPU bottleneck and higher batch count do not guarantee better learning.

## Evaluation interpretation

Frozen initial policy is a deliberately weak control. Use it to check basic learning, then Nexto as a stronger fixed opponent; compare actual W/D/L and goals. A 120-game scenario panel has substantial uncertainty. Its contexts reset to their declared situation after each goal and are not a tournament result. The 2,000-game match panel uses fresh paired-color seeds with 100-second timeouts. A candidate whose lower 95% score bound exceeds .5 is better than that tested baseline under those rules, not automatically better than strong bots or in all game modes. Repeatedly checking the same candidate/panel is discovery, not fresh confirmation. No files are automatically promoted or substituted.

## Error recovery

`0_SETUP.bat` requires Windows x64 Python 3.11, usable existing Torch and collision meshes. If automatic discovery misses the right runtime, run your known Python explicitly:

```
"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" tools\setup_project.py --python "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe"
```

For missing meshes set `DUELFORGE_MESHES` to an existing Soccar collision-mesh folder, or create `local_paths.json` containing `{"meshes":"E:/path/to/collision_meshes"}`. Assets are reused, not bundled or downloaded. A missing checkpoint is an error; no fallback bot is shown. Viewer errors are visible, and successful watch clips can be opened later with menu 8. CLI headless recording is available: `_RUN.bat watch --run duel01 --headless --seconds 30`.

Never delete checkpoints to fix a library or viewer error. Reports omit weights; preserve the whole run locally. Long-term competitive progress is an experimental question, not a promise of this release.
