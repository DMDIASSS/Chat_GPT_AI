SLATER v0.2.8 — INDEPENDENT HELD-OUT NEXTO EVALUATOR
===================================================

Scope: read-only comparison of Cycle9 against a trained v0.2.7 candidate,
both Blue and Orange, against frozen verified original Nexto. First goal or
timeout, not an actual five-minute Rocket League match. The 58.6% prior
full-match benchmark is NOT directly comparable.

Why: Slater u60 peaked at 10/16 wins in the built-in first-goal evaluation,
while u80 fell to 1/16. The original Cycle9 baseline shifted between passes,
so new held-out kickoff seeds and reproducibility checks are mandatory.

Extract this archive into E:\Downloads\Chat_GPT_AI without deleting any
existing project or checkpoint files.

1. Offline tests:
 .venv\Scripts\python.exe -m pytest slater_v028_tests -q

2. Short integration smoke (4 seeds, 120 decisions = max 8 s per game):
 .venv\Scripts\python.exe slater_nexto_heldout_eval_v028.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 4 --max-episode-steps 120 --out data/isolated/nexto_heldout_v028_smoke01.json

3. Primary held-out evaluation (24 new seeds, both sides = 48 games each):
 .venv\Scripts\python.exe slater_nexto_heldout_eval_v028.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 24 --max-episode-steps 450 --out data/isolated/nexto_heldout_v028_u60_24.json

Optional additional comparison (more games / more runtime):
 .venv\Scripts\python.exe slater_nexto_heldout_eval_v028.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --extra data/isolated/slater_v027_campaign01_u0040.pt --extra data/isolated/slater_v027_campaign01_u0080.pt --seeds 24 --max-episode-steps 450 --out data/isolated/nexto_heldout_v028_all_24.json

The evaluator checks BOTH source SHA hashes and loads candidates read-only;
no optimizer, training, promotion or overwrite. Every report must have a new
output filename under data/isolated. It checks repeated baseline replay
outcomes before and after the comparison; if the check fails, results cannot
be treated as reliable (and the script refuses to save its comparison).

The script seeds BOTH Python random and NumPy random per game to correct
one likely cause of v0.2.7 eval inconsistency. No actual Windows RocketSim
integration test was possible in the author's offline environment.

Inspect output OVERALL, PAIRED_VS_ORIGINAL, BY_SIDE.
Do NOT automatically promote u60 based on a 16-game validation result.
