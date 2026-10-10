Independent Nexto benchmark v1

1. First, BACK UP your current data/autoleague/champion.pt and league_state.json somewhere safe.
2. Unzip these three files INTO YOUR ORIGINAL E:\Downloads\Chat_GPT_AI folder
   so independent_nexto_benchmark.py is beside auto_league.py.
3. Ideally stop AutoLeague with Ctrl+C first, so no promotion happens during this test.
4. Double-click INDEPENDENT_BENCHMARK.bat. It evaluates your existing accepted champion
   against original Nexto on 200 NEW first-goal episodes with paired team sides.
   It also evaluates original Nexto against itself for a small 40-episode control.
5. A compact JSON report is created in benchmark_reports/. Send that report back.

IMPORTANT: This is NOT a 5-minute match benchmark; it is a read-only held-out test
matching the current AutoLeague first-goal scoring convention. It does not train,
delete, overwrite, promote or blacklist models. It does not touch the AutoLeague
state/history/backup directories. It DOES write an independent JSON report outside
those directories. To avoid even that, run the Python script with --no-save.

For a quick technical smoke test, run:
  .\.venv\Scripts\python.exe -u independent_nexto_benchmark.py --pairs 2 --baseline-pairs 2 --no-save

To repeat a larger independent benchmark with a different seed:
  .\.venv\Scripts\python.exe -u independent_nexto_benchmark.py --pairs 200 --baseline-pairs 30 --seed 74192018

Caution: CPU evaluation can take time, depending on your system.
