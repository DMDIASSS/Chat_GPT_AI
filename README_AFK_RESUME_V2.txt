CHAT GPT AI: AFK TRAINER VERSION 2 - SAFE PAUSE & RESUME
=======================================================

INSTALL:
  1. STOP any old running AFK job before replacing afk_two_hour.py.
  2. Extract all files from THIS ZIP into E:\Downloads\Chat_GPT_AI, choosing REPLACE for the
     existing afk_two_hour.py and leaving all data/ checkpoint folders alone.
  3. Run AFK_2H_0_CHECK.bat. Then use the commands below.

COMMANDS (double-click; do NOT run as administrator):
  AFK_2H_1_START.bat    new 120-minute job; retests the starting models
  AFK_2H_3_PAUSE.bat    requests pause; it finishes a saved PPO rollout first
  AFK_2H_2_RESUME.bat   resumes latest paused/interrupted run with another 120-minute
                        wall-clock allowance, without redoing preliminary tests
  AFK_2H_PACKAGE_REPORTS.bat  pack logs/report for ChatGPT, no weights

IMPORTANT PAUSE:
  - With the trainer running, open AFK_2H_3_PAUSE.bat in a *second* window.
  - DO NOT close the training CMD window until it prints PAUSED.
  - On a pause, the current isolated league keeps candidate.pt including its
    actor, critic, and optimizer states saved at the last PPO rollout.
  - Ctrl+C or killing the process is an emergency alternative, but may discard
    the current unsaved rollout. Automatic resume works for old v1 interrupted
    runs too, provided PRE_BENCHMARK and INPUTS were already saved.
  - Wait if currently doing the preliminary/final benchmark; pause takes effect
    at a stage boundary or after a saved training rollout, not mid-evaluation.

RESTARTING:
  - RESUME uses the existing saved league and cached preliminary match results.
  - It gives that run a FRESH 120-minute session with post-test time reserved.
    It does NOT claim to resume exactly the remaining minutes from the old run.
  - It REFUSES completed runs, smoke tests, changed source champion, moved or
    hash-mismatching model inputs, and unexpected champion-state mismatches.
  - After a normal 2-hour finish, there is no active run to resume; create a new
    experiment or ask for a continue-training variant.

OUTPUT / SAFETY:
  data/afk_runs/TIMESTAMP/league/candidate.pt    partially trained model
  data/afk_runs/TIMESTAMP/league/champion.pt     last accepted local winner
  data/afk_runs/TIMESTAMP/PRE_BENCHMARK.json     tested starting models
  data/afk_runs/TIMESTAMP/TRAIN_PROGRESS.json   last saved rollout
  data/afk_runs/TIMESTAMP/POST_BENCHMARK.json    final comparisons
  data/afk_runs/TIMESTAMP/STATUS.json            stage: training/paused/complete
  data/afk_runs/TIMESTAMP/AFK_LOG.txt            timeline

  Main data/autoleague champion/state/candidate are never intentionally edited.
  No automatic promotion to main league. Rollouts are checkpointed every
  args.rollout decisions (512 by default), plus historical backups.
  Replay downloading and replay imitation training remain OFF here. This is
  on purpose: the existing replay converter does NOT provide validated action
  labels for the native Nexto architecture, so do not feed it unsupervised.
  Evaluation is first-goal/decision-cap, not complete five-minute matches.

OPTIONAL COMMAND LINE:
  .venv\Scripts\python.exe -u afk_two_hour.py --resume-run "data\afk_runs\20261009T121833_544323Z" --minutes 120
  .venv\Scripts\python.exe -u afk_two_hour.py --resume-latest --minutes 60

NOTES:
  - Do not run multiple jobs at once. Keep your computer awake and plugged in.
  - Training can slightly exceed the requested time while finishing a rollout
    or model evaluation. If no test result improved, preserve prior champion.
