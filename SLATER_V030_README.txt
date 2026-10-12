SLATER v0.3.0  —  RLBot export + simulated 5-minute Nexto benchmark
===================================================================

What it does
------------
1. Converts verified v0.2.7 Cycle9-derived PPO actor weights (.pt training
   checkpoint) to a standalone TorchScript model loadable by the existing
   RLBot v4 Bot_Dias agent.py (which expects nexto-model.pt).
2. Provides a read-only, multi-goal five-minute RocketSim evaluation against
   frozen Nexto: both sides, seed-matched kickoff, repeat-baseline determinism
   checks, regulation clock, goal scoreboard, and capped sudden-death overtime.
3. Compares original Cycle 9 to u60, optionally u40/u80, without overwriting
   ANY protected model. NO model is automatically promoted.

Files must be extracted to your existing E:\Downloads\Chat_GPT_AI directory
alongside previously installed Slater v025, v026_fixed, v027, v028 scripts
and local modules from your original project.

RECOMMENDED CHECKPOINT (trained u60):
 E:\Downloads\Chat_GPT_AI\data\isolated\slater_v027_campaign01_u0060.pt
 SHA256: 5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74

1. Offline unit tests
---------------------
 cd /d E:\Downloads\Chat_GPT_AI
 .venv\Scripts\python.exe -m pytest slater_v030_tests -q

2. Export to RLBot v4 package (CREATE ONLY)
------------------------------------------
 .venv\Scripts\python.exe slater_export_rlbot_v030.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --out data/isolated/slater_u60_RLBOT_nexto-model.pt

 The output here is a TorchScript actor, unlike the training .pt. Make a COPY
 of your existing Bot_Dias RLBot v4 folder, then copy this exported file into
 that NEW bot folder named "nexto-model.pt" (overwrite only the copy's model).
 The current Bot_Dias agent.py loads nexto-model.pt and uses the 90-action
 Nexto vocabulary. Do not use this file as a replacement for the original
 v027 training checkpoint. The export does not overwrite the original bot.
 This package does not install RLBot or port the bot to RLBot v5.

3. Multi-goal match quick integration test (shortened 20-second game)
-------------------------------------------------------------------
 .venv\Scripts\python.exe slater_fullmatch_eval_v030.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --regulation-seconds 20 --overtime-seconds 0 --out data/isolated/v030_match_smoke_01.json

4. Actual simulated five-minute match benchmark, Cycle9 vs u60
--------------------------------------------------------------
 .venv\Scripts\python.exe slater_fullmatch_eval_v030.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 8 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v030_match_u60_8seeds_01.json

 For a larger, multi-checkpoint comparison (costs more compute):
 .venv\Scripts\python.exe slater_fullmatch_eval_v030.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --extra data/isolated/slater_v027_campaign01_u0040.pt --extra data/isolated/slater_v027_campaign01_u0080.pt --seeds 16 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v030_match_all_16seeds_01.json

Interpreting results
--------------------
 OVERALL = wins/losses/draws, scored/conceded, points rate, both sides combined.
 PAIRED_VS_ORIGINAL = seed-paired bootstrap differences vs original Cycle9.
 BY_SIDE = separate Blue vs Orange results.

The previous 58.6% win rate against Nexto was observed under a DIFFERENT
benchmark. This test is a MORE comparable 5-minute simulated match format than
v027's 30-second first-goal evaluations, but it remains a RocketSim
APPROXIMATION: each goal causes an immediate seeded kickoff reset with no goal
celebration, clock stoppage, RLBot latency, or actual Rocket League process.
Overtime has a finite cap and may therefore leave draws. It is NOT an exact
reproduction of an RLBot full-match benchmark. For a valid 58.6% -> 90% claim,
run original Cycle9, u60, and the frozen Nexto in the exact original RLBot
match harness with enough independent games, same settings and both sides.

Safety and provenance
---------------------
- Source Cycle9 and vendor Nexto SHA256 checks are mandatory.
- Only SHA-compatible, v027 stage actor dict checkpoints under data/isolated.
- TorchScript export creates a NEW .pt file only, refuses existing filenames.
- Evaluation creates a NEW .json file only, refuses existing filenames.
- The original Cycle9/champion/vendor Nexto/replay files are never modified.
- Script and integration tests passed offline, but the first actual RocketSim
  end-to-end Windows run remains unverified until run on your PC.
- Do not use RLBot models in public online matchmaking.
