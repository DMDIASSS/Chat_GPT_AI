SLATER v0.2.9 — WATCH ACTUAL ROCKETSIM GAMES (READ-ONLY)
=========================================================

WHY THIS EXISTS
The v0.2.7 evaluation has major uncertainty: very few goals, frozen original's
results drifted between evals, and Blue/Orange performance differs. Before
claiming the new bot is stronger, WATCH the same simulation it is evaluated on.

This script imports the EXACT evaluation classes:
  slater_cycle9_native_ppo_v025.Native1v1 (student as Blue),
  slater_cycle9_paired_eval_v026_fixed.RoleSwap1v1 (student as Orange),
  slater_cycle9_paired_eval_v026_fixed.greedy_action.
Both models play frozen original Nexto. This is an ACTUAL RocketSim rollout,
not an animation synthesized from log summaries. The HTML replays the physical
positions directly returned by RocketSim at every 8-tick decision.

NO TRAINING / NO PROMOTION / NO MODIFICATION TO CYCLE 9 OR NEXTO.
All output files are new HTML under data/isolated. Keep original backups.

REQUIREMENTS
  Windows CMD from E:\Downloads\Chat_GPT_AI (project root)
  Existing Python .venv, Slater project modules, verified Cycle9 and Nexto
  v0.2.5 script and v0.2.6 fixed paired evaluator
  Candidate under data/isolated (u60 recommended)

1. UNZIP INTO PROJECT ROOT AND TEST
  .venv\Scripts\python.exe -m pytest slater_v029_tests -q

2. CREATE SIDE-BY-SIDE OFFLINE BROWSER REPLAY (NO INSTALLS)
  .venv\Scripts\python.exe slater_watch_sim_v029.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --side blue --seed 1700420699 --max-episode-steps 450 --out data/isolated/slater_watch_v029_blue01.html

  start data\isolated\slater_watch_v029_blue01.html

  Watch both ORIGINAL Cycle 9 and TRAINED u60 play the SAME frozen Nexto on
  the SAME seed as Blue. The player has pause, timeline scrubbing, and speed.
  This is an overhead 2D projection of true 3D state; displays height (Z),
  orientation, ball path, controls, boost, speed, and goal events.

3. REPEAT AS ORANGE (USE NEW FILE NAME)
  .venv\Scripts\python.exe slater_watch_sim_v029.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --side orange --seed 1700420699 --max-episode-steps 450 --out data/isolated/slater_watch_v029_orange01.html
  start data\isolated\slater_watch_v029_orange01.html

4. OPTIONAL: WATCH LIVE IN RLViser, A REAL 3D ROCKETSIM STADIUM VISUALIZER
  This is NOT the Rocket League game client. It displays RocketSim state.
  Docs: https://rlgym.org/Rocket%20League/training_an_agent/
  Viewer: https://github.com/VirxEC/rlviser/releases

  If the RLGym RLViser renderer is not installed, install its dependencies:
    .venv\Scripts\python.exe -m pip install "rlgym[rl-rlviser]"

  You may also need the Windows RLViser executable from the official releases
  page, placed in your project working directory as rlviser.exe. RLViser-py
  launches its renderer binary on the first render call. Follow the release's
  Windows usage notes. The HTML mode requires NONE of this.

  Watch u60 as Blue:
    .venv\Scripts\python.exe slater_watch_sim_v029.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --policy candidate --side blue --seed 1700420699 --max-episode-steps 450 --viewer rlviser --speed 1

  Watch original Cycle9 as Blue, same seed:
    .venv\Scripts\python.exe slater_watch_sim_v029.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --policy original --side blue --seed 1700420699 --max-episode-steps 450 --viewer rlviser --speed 1

  RLViser may not launch without a compatible viewer executable, or if the
  renderer package has changed. Windows RLViser integration is NOT locally
  verified; the HTML mode was unit-tested without RocketSim installation.

WHAT TO CHECK
  - Kickoffs: Blue from negative Y attacks top positive-Y goal; Orange
    from positive Y attacks bottom negative-Y goal. Both cars should move.
  - Compare original vs u60 on matching kickoff. What is each car doing?
  - Is car steering visibly wrong? Does Nexto drive at the ball properly?
  - Are goals shown when the ball crosses into a net? Many games time out.
  - Look for teleporting / impossible speed / collision glitches.
  - Try several OTHER kickoff seeds, using unique .html filenames.

CAVEATS
  - Current evaluator stops after one goal or max steps (450=30 seconds).
  - The HTML playback is not a game engine; it draws true simulator samples.
  - RLViser is 3D and better for jumps, recoveries and aerial mechanics.
  - No 5-minute match is modeled by this tool. We still need regulation games
    to validate the claimed ~58.6% original baseline vs 90% objective.
