SLATER v0.3.0.1 — RocketSim reproducibility hotfix and probe
==============================================================

WHAT WAS WRONG
v0.3.0 reused a single RocketSim Arena across repeated matches and goals.
RLGym's RocketSimEngine.set_state recreates cars within the existing Arena;
this cannot be assumed to reset all physics-engine hidden state. On the
user's machine, the same kickoff seed gave different touch counts and
sometimes different goal event times. The original benchmark correctly
refused to report an unreliable win rate.

WHAT CHANGED
- For every new match AND every new kickoff, construct a fresh RocketSimEngine,
  TeamObserver, Native1v1 / RoleSwap1v1, and physical arena.
- Keep the same Cycle9, Nexto, actions, greedy decision logic, scorekeeping.
- Fingerprint detailed kickoff state (car jump/flip flags and boost pads too).
- Still compare duplicate games strictly; if they diverge, STOP and diagnose.
- Add a read-only same-seed action/observation/physics divergence probe.
- RLBot TorchScript export from v0.3.0 was already successful; no re-export.

INSTALL
Unzip into E:\Downloads\Chat_GPT_AI with these scripts at project root.
No files from v0.3.0 need deletion.

TESTS
.venv\Scripts\python.exe -m pytest slater_v0301_tests -q

QUICK REPRODUCIBILITY DIAGNOSIS (no checkpoint writing)
.venv\Scripts\python.exe slater_sim_divergence_probe_v0301.py --steps 300

SHORT MULTI-GOAL BENCHMARK (20 simulated seconds, first 2 seeds)
.venv\Scripts\python.exe slater_fullmatch_eval_v0301.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v0301_match_smoke_01.json

FULL COMPARISON (only if repeatability probe PASS)
.venv\Scripts\python.exe slater_fullmatch_eval_v0301.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 8 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v0301_fullmatch_u60_01.json

CAUTIONS
- These simulated matches are not identical to Rocket League RLBot matches.
- No progress claim toward 90% until verified against original 58.6% protocol.
- v0301 not integration-tested in Windows/RocketSim. If divergent outputs
  persist, save the PROBE logs; do NOT remove the determinism check or silently
  disregard unexplained differences.
- All outputs must be new filenames under data/isolated. No checkpoint writes.
