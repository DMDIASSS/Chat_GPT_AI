# Frozen candidate versus original: 200 games, 100 seconds

Close the viewer and keep training paused. Merge the complete update into your existing Chat_GPT_AI folder, including gigaforge/native and novaforge. Keep runs, environments, exports and models. Run 9_VERIFY.bat, then 20_WDL_BEST_VS_ORIGINAL_200x100.bat.

If a batch launcher does not start, open Command Prompt in gigaforge and run:

```bat
".\.venv_native\Scripts\python.exe" -u run.py h2h --run research02 --rounds 200 --seconds 100
```

The selector ranks positive confirmation-test differences across Chronos and Galactus and chooses the highest whose exact recorded weights still exist. Missing trials are skipped, with attempts recorded in the result. Trial 62 cannot be reconstructed from its score. Based on the last report and your successful watch, Chronos trial 38 is the likely available candidate; the console prints the actual selection before testing. A positive previous score is not proof of improvement.

The chosen actor plays only its own frozen public original, with matching hitboxes: Breakout for Chronos, Octane for Galactus. There are exactly 200 scored games: 100 per team color, paired on 100 fresh kickoff seeds. Each game lasts 100 simulated seconds, permits multiple goals, and ends in a draw if tied at timeout. No overtime. The evaluator batches 50 games at a time with batched inference and parallel physics. It creates no additional baseline games and does not open RLViser. The native log prints simulated progress; wall-clock time depends on your PC.

The test performs no learning or promotion. It verifies actor logits before starting and checks frozen file hashes between batches. Training STOP files, optimizer checkpoints and champions remain unchanged. Ctrl+C pauses this test; running the same command resumes completed batches without counting them twice. An interrupted incomplete batch restarts. To deliberately run an independent new test, specify another --seed, for example --seed 1581000000. A completed test with identical arguments reuses its recorded results.

Results: runs/research02/latest_h2h.json and runs/research02/h2h/<test-id>/test.json, games.csv and batch logs. The console reports W/D/L and goal totals every completed batch. The JSON also includes per-color counts and a paired-seed approximate 95% match-score interval. Match score is (wins + 0.5*draws)/games. An interval containing 50% remains uncertain. These head-to-head results do not establish improvement against every bot, and no champion is promoted automatically. Send latest_h2h.json for review; 8_REPORT also includes the test records.

Validation uses public frozen teachers as synthetic test candidates, not your private trained weights. It checks unavailable-best fallback, exact game counts, full 100-second games, both colors, resumption, export-only native logit parity and unchanged paused training state. This validates the test machinery, not your candidate's strength.
