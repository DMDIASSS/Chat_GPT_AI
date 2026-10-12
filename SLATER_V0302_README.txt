Slater v0.3.0.2 — kickoff-signature tuple fix
==============================================

CAUSE
The v0.3.0.1 signature builder tried float(value) on every car flag.
In the installed RocketSim/RLGym release at least one car field is a
numeric tuple (likely wheels_with_contact), so the determinism probe
crashed before it could run.

FIX
Handle scalar, tuple, list, and ndarray numeric fields uniformly,
including every component in the state checksum. Do not omit fields,
relax deterministic matching, or touch any checkpoints. Both updated
scripts have NEW names to avoid overriding previous versions.

INSTALL
Extract this ZIP into E:\Downloads\Chat_GPT_AI (project root).

TEST
.venv\Scripts\python.exe -m pytest slater_v0302_tests -q

REPRODUCIBILITY PROBE — run this first
.venv\Scripts\python.exe slater_sim_divergence_probe_v0302.py --steps 300

SHORT BENCHMARK — only if all PROBE rows say deterministic=true
.venv\Scripts\python.exe slater_fullmatch_eval_v0302.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v0302_match_smoke_01.json

LONGER BENCHMARK — only if the smoke test gives both PASS messages
.venv\Scripts\python.exe slater_fullmatch_eval_v0302.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 8 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v0302_match_u60_01.json

Expected: the previous TypeError about float(tuple) is gone. The
actual deterministic behavior of the Windows RocketSim engine is STILL
UNVERIFIED; if any PROBE row says false or the benchmark raises
NONDETERMINISTIC_MATCH, stop and provide the probe output.

v0.3.0 RLBot export was successful and does not need to be repeated.
No training, no model writing, no promotion, no original file changes.
