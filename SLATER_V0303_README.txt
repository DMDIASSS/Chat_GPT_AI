SLATER v0.3.0.3 — PROCESS-ISOLATED ROCKETSIM BENCHMARK

Why this patch:
v0.3.0.2 passed the 300-step deterministic probe and repeated full matches at
startup, but the frozen Cycle 9 baseline drifted after running the candidate.
It is unsafe to assume that simply recreating RocketSim arenas isolates every
native, TorchScript, or RNG side effect. This patch runs EVERY MATCH in a
SEPARATE PYTHON PROCESS, resetting all process-global state. We do not claim
this diagnoses the exact source of the earlier drift.

Extract into E:\Downloads\Chat_GPT_AI. Keep all prior scripts and checkpoints.

1. Local tests:
.venv\Scripts\python.exe -m pytest slater_v0303_tests -q

2. Reproducibility + matched-seed 20-second smoke test (fresh report name):
.venv\Scripts\python.exe slater_fullmatch_eval_v0303.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v0303_match_smoke_01.json

3. If PASS, full five-minute multi-goal benchmark:
.venv\Scripts\python.exe slater_fullmatch_eval_v0303.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 8 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v0303_match_u60_8seeds_01.json

Results: OVERALL, PAIRED_VS_ORIGINAL, BY_SIDE.

Strict guards remain: checksum-pinned original Cycle9 and Nexto; no training,
checkpoint edits, auto-promotion or reused report names. Child processes do not
write files. Workers each load model weights from safe existing paths.

IMPORTANT: Offline tests cannot validate real RocketSim on Windows. This run
is its first full integration test. If NONDETERMINISTIC_ISOLATED_MATCH occurs,
STOP and provide the full error. The cause would remain unresolved; do NOT
skip the safety checks. Per-game process spawning has extra startup overhead.

Matches use 8-tick 90-action greedy policy and multi-goal RocketSim; no kickoff
countdown, RLBot agents, or Rocket League server physics. They do NOT reproduce
the original 58.6% RLBot full-match benchmark exactly.
