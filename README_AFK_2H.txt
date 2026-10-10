CHAT GPT AI: 2-HOUR AFK EXPERIMENT (VERSION 1)
=============================================

INSTALL:
  1. STOP the old AutoLeague, tournaments, and any other training scripts.
  2. Extract this ZIP DIRECTLY into E:\Downloads\Chat_GPT_AI\ (same level as auto_league.py).
  3. Run AFK_2H_0_CHECK.bat first. It verifies champion state and required checkpoint files.
  4. Optional: run AFK_2H_SMOKE_TEST.bat, then close that window before the real run.
  5. Run AFK_2H_1_START.bat and leave it open.
  6. Make sure Windows won't sleep/hibernate when plugged in. Plug in the laptop/desktop.
  7. After returning, run AFK_2H_PACKAGE_REPORTS.bat and upload AFK_UPLOAD_THIS.zip.

WHAT IT DOES:
 - Takes SHA-verified copies of the accepted champion, tournament cycle09, and wavedash checkpoint.
 - Performs independent fresh-seed checks against ORIGINAL Nexto, direct finalist matches,
   and a Nexto-vs-Nexto sanity control.
 - Selects a starting model using 80% score vs Nexto and 20% head-to-head score.
 - Starts ORIGINAL safeguarded AutoLeague PPO in a SEPARATE new data/afk_runs/TIMESTAMP/league.
 - Uses 55% self-play, 25% cloned champion, 20% original Nexto opponent.
 - Runs guarded, isolated training until the reserved post-evaluation window.
 - Saves its candidate at least once per PPO rollout; backups every 5 minutes and at cycle boundaries.
 - Runs fresh-seed post checks of original finalists, final isolated champion and partial candidate.
 - Writes status and reports in data/afk_runs/TIMESTAMP, completely separate from live AutoLeague.

IMPORTANT SAFETY:
 - Never overwrites data/autoleague/champion.pt or league_state.json or existing candidate.pt.
 - Does NOT promote the result into your real league; don't manually replace your live champion yet.
 - Main league is locked while AFK run is active to prevent accidental concurrent AutoLeague.
 - If stopped mid-cycle, the latest saved candidate remains in the AFK league, ready for recovery.
 - Replays are DISABLED in this run because existing AutoLeague replay worker DOWNLOADS
   replay files; it does not use them directly as PPO training samples.
 - This is a 1v1 first-goal benchmark, NOT real five-minute Rocket League matches.
 - The 2-hour budget is approximate: evaluations finish at match boundaries, and
   unexpectedly slow simulations may cause runtime to slightly exceed the target.
 - Never run as Administrator. Do not run two AFK jobs simultaneously.

RESULTS:
 data/afk_runs/<timestamp>/STATUS.json             live status / error
 data/afk_runs/<timestamp>/AFK_LOG.txt             operation log
 data/afk_runs/<timestamp>/INPUTS.json            input checkpoints/hashes
 data/afk_runs/<timestamp>/PRE_BENCHMARK.json     baseline evaluation
 data/afk_runs/<timestamp>/league/champion.pt     best promoted checkpoint in isolated league
 data/afk_runs/<timestamp>/league/candidate.pt    partial unpromoted candidate, if still present
 data/afk_runs/<timestamp>/league/backups/*.pt    safeguarded backups
 data/afk_runs/<timestamp>/league/reports/*.json  internal AutoLeague decisions
 data/afk_runs/<timestamp>/POST_BENCHMARK.json    fresh independent evaluation
 data/afk_runs/<timestamp>/SUMMARY.json           concise final ranking

Any process crash should be accompanied by STATUS.json and ERROR_TRACEBACK.txt.
The training history / checkpoints remain even if the outer AFK launcher stops unexpectedly.

Only sources from THIS project are used; no change to mechanics labs or 92-input student.
