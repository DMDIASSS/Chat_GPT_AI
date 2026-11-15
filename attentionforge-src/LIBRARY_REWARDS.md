# AttentionForge 0.7 — library rewards only

Pause the existing trainer, wait for PAUSED_AND_SAVED, then close trainer/watch Python windows. Extract this ZIP into E:\Downloads so its chat_gpt_ai folder merges with Chat_GPT_AI. Run E:\Downloads\Chat_GPT_AI\attention_skills\LIBRARY.bat, option 1.

The first start copies runs/skills01/latest.pt into a NEW runs/library01. It preserves the actor, critic, Adam moments/steps/LR, counters and historical opponents. Original runs and environments are not overwritten. No random model or alternative parent is substituted if skills01 is missing. To explicitly start from your trained attack01 instead, use option 9 before library01 exists. Further option 1 starts resume library01. Check the printed LIBRARY_FORK_READY parent/provenance once.

## Exactly five published definitions

| Definition | Source | Parameters / outer weight |
| --- | --- | --- |
| GoalReward | rlgym-rocket-league 2.0.1 | scorer +1, opponent -1; weight 10 |
| AdvancedTouchReward | rlgym-tools 2.6.5 | touch_reward=0.05, acceleration_reward=0.5, use_touch_count=False; weight 1 |
| VelocityPlayerToBallReward | rlgym-tools 2.6.5 | include_negative_values=False; weight 0.2 |
| GoalViewReward | rlgym-tools 2.6.5 | gamma equals PPO gamma; weight 1 |
| AerialDistanceReward | rlgym-tools 2.6.5 | default parameters, normalization=1/5120; weight 2 |

GoalReward comes from RLGym core; RLGym-tools does not duplicate it. These are vectorized adaptations, compared against the actual installed upstream Python classes. The selected weights are an experimental preset chosen here, not an official recipe or the unpublished Chronos/Galactus training recipe.

Goals count immediately. Touch acceleration uses change in ball velocity / 6000 only when that car touched. Approach is velocity along the car-to-ball direction / 2300 times elapsed simulated seconds. GoalViewReward uses apparent goal-mouth solid angles as a geometric potential; it is not a learned scoring-probability model. Its upstream terminal behavior (probability 1/0 at a goal) is preserved literally. AerialDistanceReward pays for an elevated first touch and distance between subsequent aerial touches, resetting ownership on landing/opponent touches. Empty jumps, spinning or airtime alone earn no aerial reward. This encourages useful air contacts; it does not teach a flip reset by itself.

Source definitions:
- https://github.com/RLGym/rlgym/blob/main/rlgym/rocket_league/reward_functions/goal_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/advanced_touch_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/velocity_player_to_ball_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/goal_prob_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/aerial_distance_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/math/solid_angle.py

Apache-2.0 attribution: RLGym / RLGym-tools contributors. See LICENSES/RLGym-Apache-2.0.txt. The undefined zero-distance normalization cases receive finite guards. No extra clipping, negative-opponent shaping or per-tick bonus was added. The parity tests use rlgym-rocket-league==2.0.1 and rlgym-tools==2.6.5; training does not need to install them again.

## Removed from this run

Custom aim/shot, combo, possession, launch, flip, recovery, no-floor and face-ball rewards are disabled. Ground tutor and mechanics rehearsal auxiliary losses are disabled. Reward stages, skills drills as training resets and attack reset mixtures are disabled. Native reward outputs are zeroed before the library calculation, and reward telemetry contains only the five terms. Other launchers retain their original profiles for compatibility.

The existing native default kickoff/varied-ground reset distribution remains. GoalViewReward and AerialDistanceReward do not change physics, observations, action tables, delay, model architecture, LR or hitbox. Both cars are Octane, 120Hz physics / 15Hz decisions with one tick action delay. Self-play and existing historical-opponent sampling remain.

## Train, inspect and export

1. LIBRARY.bat -> 1 starts/resumes until you pause. Existing W&B credentials are reused by the SDK; library01 gets a new run ID. No key is read into a report or printed.
2. After about 0.5–1 million NEW learning transitions, use LIBRARY_PAUSE.bat and wait for PAUSED_AND_SAVED. Watch option 2 (open play), then 3 (all five kickoffs). Blue is library01; orange is its frozen pre-update parent. Both are actual neural policies, not scripted controllers.
3. Option 6 runs 600 games at 90 seconds, balanced by color and six initial contexts, with progress printed. The six contexts are the five kickoff variants plus open play. These are repeated validation diagnostics, not a held-out promotion test. Open-play games reset to open play after goals, so center-kickoff speed alone cannot determine that score.
4. Option 4 creates AttentionForge_report_library01_*.zip in attention_skills. Send that ZIP for diagnosis; it contains metrics, config, provenance, reward component sums and evaluation logs, with no weights or credentials.
5. Option 5 exports latest actor.pt + bot.cfg and TorchScript actor.lt + bot.bot.toml. Run the exported v5 INSTALL_V5.bat, then add bot.portable.bot.toml to RLBot v5. Export checks PT/LT logits and action equality; an actual RLBot client match still needs local Windows verification.
6. Option 8 watches the exact candidate pinned by the best exploratory open-play panel. It reports its transition count and refuses missing/changed weights. A pinned candidate is not a verified champion.

Automatic contact checks run each 500k new learning transitions; a 240-game scenario panel runs each 2M. Two consecutive large contact drops or two panels below 40% macro match score pause the run. The latest actor, original parent and scenario pins remain saved; no automatic rollback or champion replacement occurs. Do not infer match skill from increasing reward totals alone.

This is a simpler controlled continuation, not a promise of pro-level play within an hour or a guaranteed improvement. Check actual open-play scoring and conceding against the preserved parent. No untested claim about Chronos/Galactus rewards is used here.
