SLATER v0.2.5 — ISOLATED CYCLE 9-NATIVE PPO
========================================

Purpose
-------
Move from read-only Cycle9 integration preflight to one small on-policy PPO
experiment against a FROZEN Cycle9 opponent in standard RocketSim 1v1.
This is NOT replay training, NOT general self-play, NOT an elite bot,
and NOT evidence of skill improvement without separate evaluations.

Preconditions
-------------
- Run in the SAME Windows project root as the passing v0.2.4 preflight:
  E:\Downloads\Chat_GPT_AI
- Existing Python .venv, RLGym/RocketSim, afk_team_research, nexto_teacher,
  slater_research.checkpoint and source Cycle9 checkpoint are already present.
- No other files need to be replaced. The ZIP contains only new v0.2.5 files.

Steps (Windows CMD)
-------------------
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v025_tests -q
.venv\Scripts\python.exe slater_cycle9_native_ppo_v025.py --updates 2 --rollout-steps 256 --eval-episodes 12 --device cpu --out data/isolated/cycle9_ppo_v025_smoke01.pt --report data/isolated/cycle9_ppo_v025_smoke01.json

Outputs
-------
PRE_EVAL_FROZEN_CYCLE9: GREEDY frozen Cycle9 vs identical frozen Cycle9.
UPDATE: on-policy PPO loss, teacher KL, entropy, goal/touch counts.
POST_EVAL_STUDENT_VS_FROZEN_CYCLE9: GREEDY student vs frozen Cycle9 on
identical kickoff seeds, measured as wins/losses/timeouts and touches.
SUMMARY: policy change, teacher unchanged, source checksum, time and metrics.

If interrupted, a .partial checkpoint may remain. Do not delete it until
checking the error; existing output files are never overwritten.
Choose a NEW output name for every run. Never supply any source checkpoint
path to --out. The script validates the path is under data/isolated.

Safety and limits
-----------------
- SHA pins verified for source Cycle9 and Nexto file at start AND end.
- Student and teacher have separate parameter storage.
- The frozen teacher is never optimized. It is also the fixed opponent.
- PPO only runs on student; independent critic is trained in parallel.
- Native 90x8 Nexto actions; 8 RocketSim ticks per action.
- Original Cycle9/champion/replays untouched. No checkpoint promotion.
- Only short 12-second 1v1 episodes, shaped score/touch/chase reward.
- No replay state reconstruction; no validation/test split read.
- This has passed OFFLINE unit tests but CANNOT be fully tested here,
  because this runtime lacks your RocketSim and Cycle9 source files.
- Expected: you may see few wins/goals in early tiny experiments.
  A higher reward or a parameter change is NOT yet proof of improvement.
- User's v0.2.4 preflight already proved the native loader, action and observation
  have compatible shapes; v0.2.5 is still a NEW runtime integration exercise.

Next engineering work, AFTER first smoke success
------------------------------------------------
1. Read actual PRE/UPDATE/POST report and confirm correct learning signal.
2. Run statistically meaningful held-out paired Cycle9 match evaluation
   over varied positions and opponent pool; ensure no catastrophic regression.
3. Extend isolated Cycle9 PPO training with parallel RocketSim workers and
   varied offense/defense/normal starts, then admit fidelity-gated replay clips.
4. Promote checkpoint only if it consistently beats protected Cycle9 on
   genuine unseen evaluations. Do not treat v0.2.5 as a promoter.
