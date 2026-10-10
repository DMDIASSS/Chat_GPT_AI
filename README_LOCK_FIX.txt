Cycle9 TEAMPLAY V2 — AFK STALE STATUS FIX
========================================

WHAT FAILED
TEAM2_0_PREFLIGHT.bat found an October 9 STATUS.json with stage=training.
That file may remain stale after an old run exits. The previous scanner wrongly
blocked all teamplay work whenever ANY historical status said 'training'.

WHAT CHANGED
teamplay_v2.py now acquires AutoLeague's REAL process-scoped OS lock:
  data\autoleague\.training.lock
It holds the lock during preflight, smoke, training, and evaluation, not just
at startup. The lock is automatically released when the process exits.

This is safer than deleting or editing old run STATUS.json files. If an AFK or
main AutoLeague trainer is actually active, training remains blocked.

INSTALL (FROM PROJECT ROOT)
1. Leave the October 10 AFK run PAUSED. Do not resume it concurrently.
2. Extract this ZIP into E:\Downloads\Chat_GPT_AI, replacing ONLY
   teamplay_v2.py (the file from the previously installed experimental ZIP).
   It also adds the optional test_teamplay_afk_lockfix.py file.
3. Run TEAM2_0_SELF_TESTS.bat (original 4 logic tests).
4. Optional regression tests:
   .venv\Scripts\python.exe -m unittest -v test_teamplay_afk_lockfix.py
5. Run TEAM2_0_PREFLIGHT.bat again.
6. Only if it passes real RocketSim 2v2 checks, run TEAM2_1_SMOKE.bat.
7. If smoke passes, then TEAM2_2_TRAIN.bat.

If the preflight now reports a live lock instead of stale STATUS.json, close
other ACTUAL training processes normally, leaving paused AFK untouched.
Do not delete checkpoints, STATUS.json, or .training.lock. Removing the lock
file does not safely stop an active process.

SAFETY
Original Cycle9/Champion/Wavedash model weights are not modified.
Teamplay candidate output stays under data\teamplay_v2\.
Does not auto-promote or overwrite RLBot exports.
