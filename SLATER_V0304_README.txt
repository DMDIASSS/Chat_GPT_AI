SLATER v0.3.0.4 — FIRST-DIVERGENCE DIAGNOSIS + STATISTICAL BENCHMARK

WHAT THE WINDOWS LOG MEANS
v0.3.0.3 compared the same frozen Cycle 9 matchup multiple times in new Python
processes. It found different contact totals (12 versus 96 touches) despite a
matching kickoff fingerprint and same score. This IS a reproducibility issue.
We cannot yet claim which subsystem causes it.

This package provides two READ-ONLY tools with different purposes:
  slater_determinism_trace_v0304.py:
    Captures state/observation/control hashes at each decision, comparing
    separate processes to locate the FIRST divergence. It does not erase or
    excuse the strict v0303 failure.
  slater_stochastic_benchmark_v0304.py:
    Separately compares frozen Cycle 9 and u60 as STOCHASTIC match outcomes,
    with matched opening positions, both sides, repeated trials, and seed-level
    paired bootstrap confidence intervals. This does NOT claim deterministic
    physics or identical RLBot rules. Use enough independent seeds before
    selecting a model; short smoke runs never certify improvement.

Extract only these new files into E:\Downloads\Chat_GPT_AI alongside the
v0.3.0.3 files. Keep all existing source/champion/replay files unchanged.

1. TESTS
  cd /d E:\Downloads\Chat_GPT_AI
  .venv\Scripts\python.exe -m pytest slater_v0304_tests -q

2. CROSS-PROCESS TRACE (DO THIS FIRST)
  .venv\Scripts\python.exe slater_determinism_trace_v0304.py --steps 300 --runs 4

   Output has 4 CROSS_PROCESS_TRACE lines (blue/orange, fixed/greedy).
   Read the first_divergence and diagnosis fields.
   If all pass, rerun with --steps 600 --runs 5: rare differences may emerge
   only after longer contact-rich play. A passed probe is not proof that all
   multi-goal matches are deterministic.

3. OPTIONAL SHORT STATISTICAL SMOKE (NO EXACT-REPEAT ASSUMPTION)
  .venv\Scripts\python.exe slater_stochastic_benchmark_v0304.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --repeats 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v0304_stochastic_smoke01.json

   This uses 16 fresh-process matches total: 2 seeds x 2 repeats x 2 teams x
   2 policies. The score estimates from two seeds are NOT meaningful.
   No checkpoint is changed.

4. FOLLOW-UP STATISTICAL BENCHMARK (IF SMOKE RUNS)
  .venv\Scripts\python.exe slater_stochastic_benchmark_v0304.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 16 --repeats 2 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v0304_stochastic_u60_16seeds.json

   This may be slow: 128 Python-worker five-minute games including overtimes.
   Consider 8 seeds initially if process setup is too expensive. Uncertainty
   may remain high even with 16 seeds. Compare in-game RLBot matches against
   the same Nexto build for the actual original 58.6% benchmark.

SAFETY AND LIMITATIONS
 - Checksums for original Cycle 9 and original Nexto are verified in the workers.
 - Only isolated .json reports can be written. The diagnostic writes none.
 - Does NOT retrain models, modify original actors or promote any checkpoint.
 - Distinct from v0.3.0.3 strict determinism check, which should continue to
   report failures if exact repeatability is not achieved.
 - Offline tests use fake match records. Real RLGym/RocketSim Windows behavior
   is NOT verified until your machine runs the tools.
 - Control hashes and six-decimal state signatures show where sequences
   diverge; they are not mathematical proof of the underlying root cause.
 - Prior short Nexto "62.5%" cannot be compared to user RLBot 58.6% full-game
   benchmark without matching game conditions.
