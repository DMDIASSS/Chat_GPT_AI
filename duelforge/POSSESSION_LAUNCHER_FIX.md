# Exact possession stage launchers

The old 41/42 launchers passed contact01/02_possession to run.py --run. That CLI
intentionally only accepts simple run names, so the commands failed before loading
a model. The fix uses tools/contact_curriculum.py --stage possession, a whitelist
selector for the existing curriculum subdirectories. Main run.py path validation
is preserved. A missing stage raises an error; active trajectory is never substituted.

Extract into E:\Downloads and merge chat_gpt_ai/duelforge. Close stopped launcher
consoles first. No model, optimizer, reward, stage pointer or W&B changes are made.

Run 42_EVALUATE_POSSESSION_VS_PARENT.bat, then 36_REPORT_CONTACT_CURRICULUM.bat.
The submitted trajectory evaluation already completed successfully; there is no
need to repeat it just to diagnose the possession launcher.

41_WATCH_POSSESSION_VS_PARENT.bat now also uses the corrected stage selector.
Blue is the exact possession student; orange is its frozen curriculum-start parent.

Preparation verification includes CLI dispatch tests, missing-stage rejection,
and an actual native four-game evaluation through the new entry point using a
small CPU checkpoint. This does not claim Windows graphical match verification.
