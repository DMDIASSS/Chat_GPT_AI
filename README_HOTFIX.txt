AUTOLEAGUE 1.1 CRASH FIX — DOES NOT CONTAIN OR MODIFY MODEL CHECKPOINTS

Issue reported on Windows:
    TypeError: Object of type float32 is not JSON serializable
    in auto_league.py -> initial_fingerprint() -> duel() -> run_gate().

Fix:
- Convert physics positions to regular Python JSON numbers (rather than using list(np.float32_array)).
- Add recursive, strict JSON conversion for NumPy scalars and arrays used by reports and history.
- Extend real RocketSim --preflight to check the exact fingerprint path that crashed.
- Add AUTO_HOTFIX_VERIFY_EVAL.bat, a no-training, read-only test of existing candidate and champion.

INSTALL:
1. Close any running AutoLeague windows.
2. Extract this ZIP directly INTO E:\Downloads\Chat_GPT_AI, agreeing to REPLACE auto_league.py.
   Do NOT delete data/autoleague/ or extract into its own subfolder.
3. Double-click AUTO_0_PREFLIGHT.bat (now additionally tests the serialization path).
4. Double-click AUTO_HOTFIX_VERIFY_EVAL.bat. It uses your existing 8192-decision
   candidate and champion; it does NOT train, promote, blacklist or write models.
5. If it passes, double-click AUTO_1_START.bat to resume continuous training.
   The trainer should resume the saved candidate and start evaluation if 8192
   decisions have already been completed. It will create new backups.

If the READ-ONLY check complains that candidate.pt is missing, that means an
experiment may have completed/been moved. Send the exact error instead of
resetting league_state.json. You can still run AUTO_2_ONE_SMALL_CYCLE.bat if needed.

NOTE: The small evaluator smoke test cannot establish policy quality. Existing
champion backups, safety hashes, and rollback logic remain unchanged.
No 1v2 or 1v3 functionality is provided by this hotfix.
