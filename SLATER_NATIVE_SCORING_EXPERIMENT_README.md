# Finite native scoring experiment

This is a separate experiment for the demonstrated gap between contact and scoring. It preserves the current model and update180. It does not promise a stronger model or replace the playing model automatically.

## Run after inspection

1. Pause campaign 15 with `NATIVE_15_PAUSE.bat` (and any other running native campaign); wait for `PAUSED`.
2. Extract `Slater_Native_Scoring_Experiment_Update.zip` into `E:\Downloads\Chat_GPT_AI`, replacing code files.
3. Run `NATIVE_2_BUILD.bat`. This changes the native binary, so old native campaigns cannot resume under it. Their model files remain intact; continuation is through copies in the new experiment. Do not delete old data/checkpoints.
4. Run `NATIVE_18_SCORING_EXPERIMENT.bat`. It reads the latest complete paused campaign-15 checkpoint, falling back to 14 if 15 is absent, and starts `scoring_experiment01`. It needs the actual local update180 .pt teacher. No human-replay re-parsing or prepared window bank is needed.
5. Use `NATIVE_18_PAUSE.bat` to save/pause and the same start launcher to resume. `NATIVE_18_STATUS.bat` prints status. The default experiment ends after three rounds of 200,000 additional learner decisions (iteration boundaries can overshoot the budget); it is not an infinite overnight campaign. A 10 GiB disk floor stops further collection/training.

## What changes

Ground scoring starts with a stationary ball about 1,200 units from the opponent goal, a correctly aligned student behind it, and a defender offset to the side. As development checks pass, difficulty increases by 0.25: starts move toward midfield, lateral variation and approach distance grow, and the defender moves toward the goal. Grounded Python checks use the corresponding geometry; simulator-version differences remain.

Ground-scoring rewards no longer pay positive car-speed/approach rewards. After a real learner contact, a discounted ball-to-goal potential shapes progress. Total positive shaping is capped at 1 per episode, below the 10-point qualified goal reward. Going backwards incurs signed shaping loss; simply moving the car, looping around the ball or consuming boost does not earn a scoring reward. Conceding still costs 10. Starts have zero ball velocity; an already incoming free goal is not used as the lesson.

Each round collects fresh frozen-update180 targets on teacher/student behavior and does bounded native teacher imitation before and after PPO. One bounded script-imitation epoch rehearses kickoff, with the shared features frozen; the learner chooses its own controls during PPO and all scoring/match checks. Opponents keep scripted kickoff. Human replay/TAS training is not repeated in this focused experiment.

Both the PPO checkpoint before teacher refresh and the refreshed checkpoint are preserved. This matters because improved teacher fit can reduce current game performance. The experiment compares incumbent, PPO-before-refresh and refreshed policies on the same fresh scoring starts and then normal 30-second games, both colors, against update180. It records a best drill specialist and a separate provisional best match model. The drill winner seeds the next focused round; the playing reference remains update180. A 75% per-color development threshold increases practice difficulty; it is not certified mastery or an independent best-model guarantee.

Reports: `data\isolated\native_scoring_experiments\scoring_experiment01\round_001\drills.json`, `ranking.json`, `games.json`, and root `status.json`. Native runs are under `data\isolated\gigalearn_native\runs\scoring_experiment01_r001`; `before_teacher_refresh\NUMBER` preserves the pre-refresh full checkpoint. Native training metrics now include actual sampled-training goals, concessions, goalward touch steps and time behind the ball. These counts are not greedy evaluation scores.

## Validation limits

Cloud integration used the uploaded initially idle native checkpoint and original Nexto as the available frozen teacher, not the unavailable local update180. An actual native build, collection, scoring PPO, pre/post refresh, 96-state inference parity, checkpoint preservation and finite completion ran. The first short experiment's refreshed model scored 4/4 close scoring cases, but still scored zero in four 30-second matches. The pre-refresh model conceded 14 in that screen versus refreshed 18 and incumbent 20. All candidates were retained. This demonstrates why drill success and teacher KL must be separated from competitive performance. Windows/GPU behavior and the user's raw replays need local validation.
