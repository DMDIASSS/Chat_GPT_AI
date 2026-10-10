CYCLE9 REPLAY DEFENSE LAB v0.1  (experimental, isolated)
======================================================

WHAT IT DOES
------------
- Reads your own Rocket League .replay files (1v1 or 2v2 only).
- Sorts replays from MOST combined shots + saves to FEWEST, when carball
  metadata exposes these counters. Unknown-stat replays are placed last.
- Detects dangerous shot-like touches using source annotations and a simple
  initial ball-velocity/goal-trajectory check (NOT a perfect shot classifier).
- For each shot creates multiple drills starting ~1.5, 3, 5 and 10 seconds
  before the shot, if the frames exist and don't cross goal/kickoff boundaries.
- In 2v2, creates one drill PER defending player. Only one defender is
  learner-controlled per repetition; all other cars follow inferred replay
  controls, not frozen/static NPCs.
- Resets the exact same initial positions/velocities and boost for every
  repetition. Runs genuine RocketSim physics afterward.
- If a *tagged save* is available and this is the defending player who made
  it, uses a VERY WEAK behavior-cloning term for inferred replay actions;
  otherwise PPO learns by attempting different defensive responses.
- Keeps the source Cycle9 checkpoint and AutoLeague training files untouched.

IMPORTANT CAVEATS
-----------------
1. Rocket League .replay files do NOT reliably contain full exact original
   controller inputs. RLGym Tools INFERS some actions, especially pitch/yaw/
   roll. Physics can drift, making complex flip resets and double taps
   impossible to reproduce perfectly from replay alone. Fidelity checks are
   required. If they fail, DO NOT TRAIN from that replay. For higher-fidelity
   training we'd want directly recorded live bot controls or in-game state
   telemetry from custom games.
2. First version attempts to reproduce attacker actions, but opponents do
   not adapt to the defender. It is scripted counterfactual practice, not a
   real human playing each attempt.
3. Successful non-goal episodes are NOT proof that a real save happened.
   Full RLBot testing vs the GC2 friend and held-out replays are necessary.
4. Preflight and unit tests were checked in code; the full .replay-to-RocketSim
   Windows pipeline CANNOT be tested here without YOUR .replay files and the
   Windows environment. There may be parsing/engine incompatibilities.
5. Do not auto-promote the candidate. Training on narrowly selected defensive
   situations can harm shooting, attacking, and real 2v2 teamwork.
6. This v0.1 validates the FIRST 30 high-priority drills per fidelity run,
   then trains those 30 only (or fewer if some fail). Scale after verifying.
7. Commercial usage/redistribution of original Nexto-derived actor weights
   is subject to upstream license and attribution restrictions.

INSTALL
-------
Extract the ZIP into:
  E:\Downloads\Chat_GPT_AI

The extracted scripts should sit next to:
  afk_team_research.py
  auto_league.py
  nexto_teacher.py
  native_nexto.py

Keep the October 10 AFK run PAUSED. Do not run TEAM2 training at same time.
Install the additional replay parser in your *existing* virtualenv:
  .venv\Scripts\python.exe -m pip install "rlgym-tools>=2.6.0" pyarrow pandas

Source: https://github.com/RLGym/rlgym-tools
It includes a bundled carball executable for Windows in current versions.

SAVED REPLAY FILES
------------------
Your replay files are typically in:
  %USERPROFILE%\Documents\My Games\Rocket League\TAGame\Demos

COPY a few .replay files (do not MOVE the originals) into:
  data\replay_defense\replays

Use your GC2 friend's 1v1/2v2 replays; for first tests, pick 2–3 with a
high number of shots and saves. No need to upload the replays to a service.

RUN IN ORDER
------------
0. REPLAY_0_TESTS.bat      -> 7 pure-Python tests (no simulator)
0. REPLAY_0_PREFLIGHT.bat  -> verifies parser, Cycle9 SHA and Nexto policy
1. REPLAY_1_EXTRACT.bat    -> sorts replays, extracts frozen start states
2. REPLAY_2_FIDELITY.bat   -> checks scripted shots in RocketSim, READ-ONLY
3. REPLAY_3_SMOKE_TRAIN.bat-> 1 attempt per accepted scene, new isolated model
4. REPLAY_4_TRAIN.bat      -> 32 attempts per scene, new isolated model
5. REPLAY_5_RESUME.bat     -> resumes the full run safely after interruption

Run full training ONLY if fidelity tests reproduce real threatening shots.
If there are no accepted drills STOP and send the console output.

Safe pause while training: in a separate CMD window run
  type nul > data\replay_defense\training\cycle9_replay_defense_v1\STOP_AFTER_REPETITION
The trainer saves a checkpoint at the next repetition boundary, exits, and
prints SAFELY PAUSED. Delete only STOP_AFTER_REPETITION before resuming.

OUTPUTS
-------
  data\replay_defense\index.json
  data\replay_defense\drills.json
  data\replay_defense\drills\*.npz
  data\replay_defense\fidelity.json
  data\replay_defense\training\cycle9_replay_smoke\candidate.pt
  data\replay_defense\training\cycle9_replay_defense_v1\candidate.pt

All these outputs are isolated experiments. The script never modifies
  data\autoleague\champion.pt
  data\autoleague\backups\...cycle0009...pt
  data\teamplay_v2\...

STATUS / NEXT MILESTONE
-----------------------
This is experimental v0.1 for validating replay shot recreation and the PPO
training loop, not a verified expert-demonstration trainer. We must review
per-drill fidelity, actual goal threats, and evaluate held-out replay saves.
If the .replay files don't reconstruct, the next correct solution is
high-frequency telemetry capture during GC2 friend's custom games or direct
controller traces, NOT relaxing fidelity thresholds until everything passes.
