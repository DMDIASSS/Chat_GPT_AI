SLATER v0.3.2 — INDEPENDENT KICKOFF HELD-OUT EVALUATION
==========================================================

This package is a READ-ONLY evaluation of the saved v0.3.1 kickoff-specialist
checkpoint versus its original frozen u60 parent. It does NOT train, export,
or promote a bot, and makes no claim about Rocket League full-match win rates.

1. Extract the ZIP contents into E:\Downloads\Chat_GPT_AI
   Keep the existing v0.3.1 scripts installed in the same project root.

2. Basic tests:
   .venv\Scripts\python.exe -m pytest slater_v032_tests -q

3. Audit the already extracted kickoff dataset. No re-extraction is needed:
   .venv\Scripts\python.exe slater_kickoff_audit_v032.py --scenarios data/kickoffs_v031

   Expected: no cross-split replay SHA leakage and no duplicate scenario keys.
   The 16 v0.3.1 FileExistsError messages are likely repeated replay files
   with the SAME CONTENT HASH, so the extraction protected against overwrites.
   This audit checks the resulting dataset; it does not mutate it.

4. Tiny smoke check on the UNUSED replay TEST split:
   .venv\Scripts\python.exe slater_kickoff_heldout_v032.py --checkpoint data/isolated/slater_kickoff_v031_run01_u0040.pt --episodes 12 --repeats 1 --max-steps 120 --out data/isolated/kickoff_v032_smoke_01.json

5. If that passes, independent heldout benchmark:
   .venv\Scripts\python.exe slater_kickoff_heldout_v032.py --checkpoint data/isolated/slater_kickoff_v031_run01_u0040.pt --episodes 60 --repeats 2 --max-steps 180 --out data/isolated/kickoff_v032_u40_test01.json

Comparison report: HELDOUT_ORIGINAL_U60, HELDOUT_KICKOFF_CANDIDATE,
PAIRED_HELDOUT_COMPARISON (win/first touch/ball progress + bootstrap CI).

Interpretation:
- Each competitor runs in its own Python process; EVERY kickoff uses a FRESH
  RocketSim arena and new TeamObserver. A new process alone wasn't sufficient
  to guarantee bit-exact determinism in the earlier full-match tests.
- Both competitors get the same replay TEST split, team side, opponent mode,
  starting pose and random kickoff seeds. Different outcomes or trajectories
  are allowed; starting-state mismatch is an error.
- Repeat evaluations use different seeds to expose variability.
- This compares controlled 1v1 kickoff slices, NOT 5-minute full matches.
- Fake takeover is a trajectory proxy, NOT semantic fake recognition.
- Existing v0.3.1 val eval reused a simulator and showed slight original
  baseline drift even before training; don't use its counts for promotion.
- A 90-action Nexto actor CANNOT express jump + diagonal pitch/yaw natively.
  These scripts don't add speedflip or half-flip abilities.
- The source u60 and Cycle 9/Nexto SHA files are verified, and output reports
  can only be created in data/isolated. Existing reports aren't overwritten.

Known limitations:
- Real native RocketSim integration requires the Windows installation;
  local tests cover logic and file guards only.
- Results may remain variable even with new arenas. Bootstrap intervals are
  descriptive and should not be treated as a final statistical certificate.
- Sample 60 episodes x 2 repeat passes = 120 episodes for EACH policy,
  spread evenly across both sides and six rollout slots.

NEXT ENGINEERING WORK AFTER HELDOUT RESULTS:
- A tick-level expanded mechanics action controller with optimized speedflip,
  half-flip and recovery macros, integrated BOTH into PPO and RLBot runtime;
  score first-ball-touch time, boost use and recovery on varied spawns.
- Opponent-league training (Wavedash, Nexto, Cycle 9, saved checkpoints),
  possession + defense reward tuning, and separate 2v2/team-aware training.
- Full-length RLBot benchmarking matching original 58.6% test conditions.
