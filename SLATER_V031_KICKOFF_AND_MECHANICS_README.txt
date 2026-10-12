SLATER V0.3.1 -- KICKOFF CURRICULUM + MECHANICS ACTION-SPACE AUDIT
==================================================================

Background: The u60 checkpoint showed encouraging small Nexto simulations but a
poor real RLBot kickoff and 2-4 sample match. One match is not a reliable
winning-rate estimate. v027 first-goal/short-horizon results are NOT comparable
to the original 58.6% RLBot benchmark. DO NOT promote v031 based on kickoff
reward or short Nexto trials alone.

Exactly what this release DOES:
  1. Extract clean pre-kickoff 1v1 STARTING POSES from original .replay files,
     using official RLGym Tools conversion/gameplay period boundaries. Not goal
     clip .npz data; this is a separate dataset. Leakage protected by replay-
     SHA train/validation/test split. Only clean 1v1 center-ball samples kept.
  2. Fine-tune a fresh, independent copy of preserved u60 in RocketSim using
     PPO with the original u60 frozen as its KL teacher.
  3. Alternate Blue/Orange, train with actual physically simulated Nexto and
     Cycle9 alongside 3 kinds of physically simulated fake-kickoff opponents:
       - idle_fake: no approach
       - turn_fake: begin normally then turn away
       - late_fake: commit normally then cut/turn late (might still touch ball)
     No teleporting ghosts. The curriculum reports if a fake opponent actually
     avoided contact; it does NOT force that result.
  4. Reward timely first touches, forward ball outcome and goals. Report a
     fake_takeover_proxy (student contact + opponent no contact + ball in
     attacked half), which is NOT a rigorous possession label.
  5. Audit the native 90-action Nexto vocabulary. Its jump-with-yaw limitation
     prevents the actual simultaneous jump+diagonal pitch/yaw dodge of a
     speedflip, so v031's PPO still CANNOT learn a proper speedflip.
  6. Send candidate tick-level diagonal dodge cancel / half-flip scripts through
     RocketSim and record physical results. They are UNOPTIMIZED PROBES and may
     fail or lift the car -- inspect them before using them as mechanics.
  7. Export a v031 checkpoint as Nexto-compatible RLBot TorchScript in a new
     file for isolated testing (without replacing old bot).

Pre-requisites: existing E:\Downloads\Chat_GPT_AI folder has v025/v026/v027,
slater_research.checkpoint, nexto_teacher, afk_team_research and original
Cycle9/u60/Nexto weights. Use existing Windows Python venv.

EXTRACT
-------
From project root:
  cd /d E:\Downloads\Chat_GPT_AI
  .venv\Scripts\python.exe -m pytest slater_v031_tests -q
  .venv\Scripts\python.exe slater_kickoff_extract_v031.py --replays data/replays --out data/kickoffs_v031

If your raw replays are stored somewhere else, replace data/replays with the
folder containing .replay files. This command only supports RAW .replay, not
*_goal*.npz. If no original replay files available, skip extraction and the
kickoff trainer can still run on procedural kickoff spawns.

Review data/kickoffs_v031/manifest_v031.json and counts. The extractor may
reject a period for insufficient temporal alignment, game type, replay speed,
or corrupted data. It never silently claims a bad snapshot is valid. Parsed
controller inputs are INFERRED and NOT used as verified supervision/fake labels.

PHYSICAL MECHANICS PROBE (OPTIONAL, new output name on each attempt)
-------------------------------------------------------------------
  .venv\Scripts\python.exe slater_mechanics_probe_v031.py --out data/isolated/v031_mechanics_probe_01.json

Actual physical performance matters: distance, speed, height, grounded state,
and 180-degree reverse alignment. The experimental timings are not claimed to
be a correct speedflip. We need an expanded hierarchical action interface to
train one as an intentional policy option.

KICKOFF FINE-TUNING
------------------
Train 40 updates on a NEW run name:
  .venv\Scripts\python.exe slater_kickoff_train_v031.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --scenarios data/kickoffs_v031 --run slater_kickoff_v031_run01 --updates 40 --rollout-steps 1024 --checkpoint-every 10 --max-episode-steps 180 --eval-episodes 36

The baseline BEFORE training compares u60 against itself on 36 paired kickoffs,
then every 10 updates compares candidate vs u60 using the same evaluation
scenarios. In current implementation no recorded replay validation data means
procedural-only evaluation; this is NOT proof of generalization to replays.

Key outputs:
  BASELINE_KICKOFF_EVAL, UPDATE, KICKOFF_EVAL, SAVED_ISOLATED, SUMMARY

Metrics: first_touch_rate, fake_takeover_proxy, fake_no_opponent_touch, wins,
losses, signed ball progress. Compare against u60; do not just maximize reward.

Checkpoint path at update 10 (example):
  data/isolated/slater_kickoff_v031_run01_u0010.pt
This is a training checkpoint; v030 exporter does NOT support it.

EXPORT FOR RLBot TESTING (after checkpoint exists)
--------------------------------------------------
  .venv\Scripts\python.exe slater_export_kickoff_rlbot_v031.py --checkpoint data/isolated/slater_kickoff_v031_run01_u0040.pt --out data/isolated/slater_kickoff_v031_RLBOT_model.pt

Copy exported model to a SEPARATE COPY of Bot_Dias package as nexto-model.pt.
No existing file is silently overwritten, and original source models remain
SHA-protected. No script modifies/replaces champion, original u60, Nexto or
original replays. Outputs use create-only filenames; changing the run name
starts an independent candidate.

NEXT RESEARCH TRACK -- NOT YET IMPLEMENTED
-----------------------------------------
 A. Extend action representation with temporal macro options for validated
    speedflip L/R, half-flip, recoveries. Train option head with physical
    benchmark + imitation then PPO. Do NOT claim the current 90-action actor
    can use those macros until deployed in RLBot too.
 B. League PPO: rotate original Cycle9, Nexto, Wavedash (once valid RLBot/
    RocketSim adapter provided), historical Slater checkpoints and self-play.
    Generalize across boost/spawn/opponent styles, avoid overfitting one policy.
 C. Replay curriculum for shots, air ball interceptions, backboard/goal line;
    replay fidelity and counterfactual gates remain mandatory.
 D. Add full 2v2/3v3 separate training and evaluate double commits, rotations,
    support spacing, role switching. 1v1 PPO cannot teach teamplay.
 E. Full-length independently seeded 5-minute games in EXACT original RLBot
    58.6% Nexto benchmark settings, both sides and enough matches to reduce
    uncertainty. Then compare directly against Cycle9/u60.

DESIGN LIMITATIONS
------------------
The local test suite uses fake state objects, not a real RocketSim runtime,
because the authoring container lacks the user's RLGym and replay dependencies.
10/10 offline tests and syntax checks passed. Windows is required for first
integration of replay extraction and physical PPO. If extraction or training
fails, record traceback and fix rather than train with silently bad data.

RocketSim and RLGym are offline testing tools; use RLBot only in permitted
custom/offline environments, not public online matchmaking.
