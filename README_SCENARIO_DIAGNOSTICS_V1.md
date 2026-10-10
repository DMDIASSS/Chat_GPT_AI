> **Updated:** see `README_SCENARIO_DIAGNOSTICS_V2.md` for the new kickoff-quality metric and dedicated kickoff launcher. The basic first-goal interpretation below remains unchanged.

# Chat_GPT_AI: Scenario Diagnostics v1 (read-only)

## Why this upgrade first?

Previous first-goal tournament results were not enough to determine **which Rocket League skills** each checkpoint lacked. For example, a model that wins many 1v1 kickoffs can be poor at saving or recovering. Small screens (`16` episodes / `6` unique starts) gave very unstable ranks: cycle 24 went from `84.4%` to `49.0%` in a longer stage.

This add-on **does not train**. It isolates scenario classes so we can select the training problem intelligently, then measure later experiments on the **same evaluator but fresh held-out seeds**. We deliberately postpone replay-based imitation because the original replay converter does not produce verified Nexto action labels.

## Install / first run (Windows)

1. Pause the AFK v2 trainer using `AFK_2H_3_PAUSE.bat` and wait for `PAUSED` (or stop AutoLeague). Do **not** run training and these CPU-heavy tests simultaneously.
2. Extract the ZIP into `E:\Downloads\Chat_GPT_AI` (root, alongside `auto_league.py` and `.venv`). It only adds new scripts.
3. Double-click `RL_DIAG_0_CHECK.bat`. It verifies checkpoint files and SHA hashes.
4. Double-click `RL_DIAG_1_SMOKE.bat` and let it finish. It executes real RocketSim tests with short episodes; smoke results are **not** gameplay evidence.
5. Double-click `RL_DIAG_2_BENCHMARK.bat` (normal) or `RL_DIAG_3_THOROUGH.bat` (longer, only if desired).
6. Send ChatGPT the resulting `data\scenario_diagnostics\scenario_diagnostics_*.json`, or a ZIP containing those JSON files.

No administrator permissions are required. If it prints an error, share the full traceback. Keep your machine awake during a long run. At any point Ctrl+C stops the evaluation (you can rerun and it will reuse **completed** seed/side pairs).

## Tested models

- `data/autoleague/champion.pt` — existing accepted champion
- `data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt` — tournament Cycle 9
- `data/mechanics/wavedash/last.pt` — Wavedash checkpoint; evaluated in normal game states, not only its special skill
- Original, frozen Nexto as common opponent and Nexto-vs-itself control

Add another native checkpoint, e.g. an isolated AFK champion, with:

```
.venv\Scripts\python.exe -u rl_scenario_diagnostics.py --pairs 8 --add-model trained="data\afk_runs\YOUR_RUN\league\champion.pt"
```

Only native Nexto actor checkpoints are compatible. The old `nexto_student` 92-feature networks cannot be loaded here.

## What it tests

Each pair has identical simulator seed and scenario and swaps the evaluated policy between Blue and Orange. A score is `(wins + 0.5 * draws) / episodes`. Every test is **first goal or 750 decisions** (~50 seconds at 15 decisions/s), **not** a five-minute Rocket League match.

- **kickoff**: Rocket League kickoff spawn positions. There are deliberately only a few unique starts; duplicates are expected.
- **ground**: random ground balls and ground-positioned cars.
- **defense**: ball plus cars positioned near defensive regions using the project's existing curriculum.
- **aerial**: elevated balls and repositioned cars; this is *not* proof of an advanced aerial or flip reset.
- **wall**: side-wall ball states, again using the project's training curriculum.

We re-use the exact `ChatGPTCurriculum` physics presets already implemented in the project, not a new physics engine. The simulated starting states are **synthetic**, not sampled from human replays.

Each scenario gets its own W/L/D results and uncertainty estimate. Confidence intervals bootstrap **paired initial seeds**, not individual Blue/Orange episodes. The report includes head-to-head matchups and relative results versus champion. Those intervals are exploratory, especially for models selected after a previous tournament.

## What this does NOT do

- Does **not** touch `data/autoleague/champion.pt`, `candidate.pt`, `league_state.json` or `data/afk_runs`.
- Does **not** update reward weights or PPO hyperparameters.
- Does **not** download replays or use a Ballchasing token.
- Does **not** run complete 5-minute matches, learn mechanics, or claim a reliable real-game win rate.
- Does **not** turn a better test score into an automatic promotion.

It uses `data/autoleague/.training.lock` to prevent conflicts and writes **only** under `data/scenario_diagnostics/` plus that lockfile. A repeated run with the same settings uses a persistent JSONL cache keyed by both checkpoint hashes, scenario and seed, and max decisions. Models are SHA-checked before/after evaluation.

## Why these choices align with Rocket League

Rocket League is a physics-control game. Decision quality is not one scalar ability. Kickoff speed/first contact, ground dribbling, defensive positioning, aerial reads, and wall situations demand different policies. Nexto itself is a strong PPO-trained attention-based bot, and our code keeps its **90-discrete-action table**, **8 physics ticks per decision** and original observation builder. The project currently trains only 1v1; it should not claim competence in 2v2/3v3.

RLGym docs cover action parsers, repeat actions, state mutators and rewards:
- https://rlgym.org/Rocket%20League/Configuration%20Objects/action_parsers/
- https://rlgym.org/Rocket%20League/Configuration%20Objects/state_mutators/
- https://rlgym.org/Rocket%20League/training_an_agent/
- https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/making_a_good_bot.md

## Roadmap after the report

1. Use scenario results to choose an **isolated** objective: kickoff, defensive recovery, aerial contact, or wall behavior. Fix objective only when benchmark evidence points to it.
2. Experiment with PPO changes in separate AFK branches: critic initialization/persistence, reward balance, and opponent diversity. Keep one variable changed at a time; use paired benchmarks against Nexto and historical checkpoint opponents.
3. Build a **replay quality audit** (rank/date/gamemode/duplicates/parse coverage). Never treat raw replay telemetry as true controller action labels without validating a reconstruction pipeline.
4. Run longer evaluations and eventually implement a proper five-minute scoreboard evaluator. Keep the main champion frozen until independent held-out wins justify manual promotion.

### License
The project derives from the original Nexto weights under CC BY-NC-SA 4.0; preserve upstream attribution/license terms when distributing derivatives.
