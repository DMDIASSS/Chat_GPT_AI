TEAMPLAY v2 -- ISOLATED shared neural policy 2v2 PPO research
============================================================

PURPOSE
Train two active Cycle9 clones as a shared neural policy against two original
frozen Nexto policy actors (~70% episodes); remaining ~30% against two frozen
Cycle9 clones. No 1-attacker/1-stationary rule-based RLBot controller.

WARNINGS
- EXPERIMENTAL: Has static tests but NOT yet validated against RocketSim on your PC.
- No guarantee training improves 2v2, much less beats two Nextos. Short
  first-goal episodes are not 5-minute RLBot matches.
- The two Nexto opponents use the pretrained *neural policy*, not the RLBot scripted kickoff.
- Original Cycle9 and the original champion are never written. Everything
  goes to data/teamplay_v2/ . Does not touch prior paused AFK experiment.
- The pretrained Nexto-based model uses about 15 policy actions/second.
- Only the policy learns. Opponents are FROZEN. Two learners SHARE weights.
- No pre-scripted permanent attacker or goalie. Tactical roles can reverse.
- The supplemental training rewards are HEURISTICS and may create exploits.
- No shooting/advanced recovery teaching yet; 2v2 coordination is the focus.
- Offline/private RLBot only; original Nexto terms CC BY-NC-SA 4.0.

INSTALL
Extract the nine files into E:\Downloads\Chat_GPT_AI beside afk_team_research.py,
nexto_teacher.py, native_nexto.py, and your .venv. This is ADDITIVE only.

RUN IN ORDER
  TEAM2_0_SELF_TESTS.bat  -> pure logic tests; stop if error
  TEAM2_0_PREFLIGHT.bat   -> 3 actual RocketSim 2v2 tests; stop if error
  TEAM2_1_SMOKE.bat       -> small 256-sample isolated PPO smoke; stop if error
  TEAM2_2_TRAIN.bat       -> 16,384 cumulative learner samples, check logs
  TEAM2_4_EVALUATE.bat    -> read-only held-out paired seeded 2v2 vs two Nextos

The training file saves after EACH rollout to
  data/teamplay_v2/cycle9_shared_2v2/candidate.pt
This checkpoint contains actor optimizer/critic metadata. It is NOT the RLBot
TorchScript export itself.

RESUME: TEAM2_3_RESUME.bat. You can request a SAFE stop after the next rollout
by making an empty file:
  data/teamplay_v2/cycle9_shared_2v2/STOP_AFTER_ROLLOUT
Then remove it and resume. Ctrl+C may lose the IN-PROGRESS rollout.

After evaluation, if the candidate outperforms Cycle9 AND remains capable in
actual RLBot games, you can export via existing project exporter:
  .venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "data\teamplay_v2\cycle9_shared_2v2\candidate.pt" --name "Cycle9_2v2_Learned"
Do not auto-promote or overwrite an existing export with the same name.
Use two separate bot registrations of that export for 2v2; both load the same
policy and dynamically see teammates in the original Nexto attention observation.

WHAT TO MEASURE IN RLBot
- Goals for/against over full 5-minute games vs Nexto + Nexto
- Double commits per game and whether they cause open-net counters
- Teammate bumps and both players' actual activity (not standing still)
- Recovery quality, positioning, and offensive play preserved
- Compare same matchups before and after, swapping team colors

If preflight fails, please send its FIRST traceback. Don't skip validation.
