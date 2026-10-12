# Slater v0.3.8b — RLBot v4 Nexto tick-scheduler simulation experiment

**Read-only experiment. Zero checkpoint writes. No PPO training.**

Your v038a Windows gates passed:
- RocketSim 8-tick batch vs eight 1-tick calls: `max_abs_error = 0.0` on 12 tested blocks (one trajectory).
- 528 of 528 same-RocketSim-state Nexto observation comparisons, zero model action disagreements (still **NOT live RLBot packet parity**).

**Result:** It is now reasonable to **experiment** with an individually stepped 120Hz Nexto controller. This release does that. It is not a claim that the live Rocket League environment has been reproduced exactly.

## New files

- `slater_nexto_scheduler_v038b.py`: pure reference-based implementation of the **control-flow order** from RLBotPack Nexto `bot.py` for `get_output()` and `maybe_do_kickoff()`. Source's native controller table is used exactly (SHA-256 `6f3b9fadf306e5f1275a149ecb672028258086586cbdd1190fe533c25248fc88`). Models the 8-tick NN refresh logic, hardcoded script, team-based kickoff taker selection, stochastic beta during kickoff pause, overwritten previous action, ball-y interruption, and kickoff-pause reset.
- `slater_nexto_tick_eval_v038b.py`: creates **new** RLGym/RocketSim environments for old and new controller paths. New path asks the controller for commands *every physics tick*, advancing RocketSim one tick before checking for an interruption. Compares the three old v037a modes with three tick-scheduler modes, for both Cycle9 and frozen u60, both sides, paired seeds.
- `slater_v038b_tests`: 16 offline tests, including a source-control-flow oracle test, exact control table boundaries, fake 8-tick RocketSim adapter test for a fourth-tick touch, plus report creation/verification checks.

## Installation

Extract to `E:\Downloads\Chat_GPT_AI`, keeping the existing Slater project modules intact. The new ZIP **does not** contain or overwrite v037a, v038, v038a files, model files, torch assets, or any checkpoints. Test and benchmark commands must be run from the project root.

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v038b_tests -q
```

Expected: `16 passed`.

## A. Inspect Nexto's script/controller schedule (no models required)

```bat
.venv\Scripts\python.exe slater_nexto_tick_eval_v038b.py trace --ticks 175 --out data/isolated/v038b_tick_trace01.json
```

Result: trace of the 168-tick kickoff schedule, controls at stage boundaries, NN update events and stochastic beta. **Does not require RocketSim or weights**. Scripted physics ticks should be `168`.

**Important:** If this output already exists, select a new filename. The tool intentionally refuses overwrite.

## B. Paired RocketSim smoke comparison (requires your existing weights and two passed gates)

```bat
.venv\Scripts\python.exe slater_nexto_tick_eval_v038b.py benchmark --seeds 2 --horizon 180 --seed 20261021 --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --physics-gate data/isolated/v038a_engine_gate01.json --obs-gate data/isolated/v038a_obs_stress01.json --out data/isolated/v038b_tick_smoke01.json
```

This runs `2 seeds * 2 sides * 6 modes * 2 student policies = 48 episodes`, each up to 180 eight-tick decisions (12 seconds), with many expected timeouts. It is an **integration/scheduling smoke check, not a win-rate estimate**. Expect `V038B_SEED_COMPLETED` messages and a final JSON summary.

Six opponent configurations:

1. `nexto_greedy` — existing v037a greedy NN, batched 8 ticks.
2. `nexto_script` — existing v037a scripted NN, batched 8 ticks, approximate pause flag.
3. `nexto_stock_approx` — existing v037a script + stochastic, batched 8 ticks, approximate pause flag.
4. `nexto_greedy_tick` — reference-ordered 120Hz NN/controller scheduling, **no scripted kickoff**.
5. `nexto_script_tick` — reference-ordered 120Hz scheduling with scripted kickoff, nonstochastic NN.
6. `nexto_stock_tick` — reference-ordered 120Hz scheduling with script and stochastic kickoff decisions.

Note that even the pure greedy tick mode could differ because the archived RLBot v4 controller's initial `update_action`/`ticks` scheduling is not exactly an 8-tick held-action policy. This is a *measurement*, not automatically a bug fix.

The evaluation report records per-policy wins, losses, **timeouts (not draws)**, script-applied physics ticks, NN inferences, and per-side paired results.

## C. Longer held-out evaluation (only after B succeeds)

```bat
.venv\Scripts\python.exe slater_nexto_tick_eval_v038b.py benchmark --seeds 4 --horizon 600 --seed 20261023 --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --physics-gate data/isolated/v038a_engine_gate01.json --obs-gate data/isolated/v038a_obs_stress01.json --out data/isolated/v038b_tick_600steps01.json
```

This is `4 * 2 * 6 * 2 = 96` single-goal episodes, each capped at 40 in-game seconds. It **can be significantly slower** than v037a because the new three modes perform per-tick engine steps and some extra NN calls.

## Limits / what is *not* solved

- RLBot's `packet.game_info.is_kickoff_pause` is **not available** in RLGym/RocketSim; this simulator uses a proxy that remains true until the first observed ball touch. Exact packet flag timing can differ.
- The real RLBot v4 bot receives packets with `round((seconds_elapsed-prev_time)*120)` timing; this simulation assumes exactly one physics tick per controller frame. Irregular frame rates or dropped packets are **not yet modeled**.
- v038a observation parity is between two builders viewing the same **simulated** state. It doesn't prove the RLGym-to-legacy packet conversion matches live RLBot data.
- The kickoff selection algorithm reproduces **the actual reference condition**, including the odd `if not is_left:` clause that may disagree with the source comment 'Left goes'. Do not silently change it.
- The scheduler uses an existing 90-action Nexto neural network for NN actions but the script's *continuous* controls are sent directly to RocketSim. The student's policy is unchanged.
- This 1v1 setup does not exercise every team-kickoff scenario; do not claim 2v2 parity.
- No exact full-game RLBot win rate can be inferred from this evaluation.
- This package contains **no training mode**. Do not promote u62 or modify working V60/OG Champion/Cycle9.

## Files to return

- `data\isolated\v038b_tick_trace01.json`
- `data\isolated\v038b_tick_smoke01.json`
- Optional `data\isolated\v038b_tick_600steps01.json`

We will inspect whether scripted controls are active for the expected ticks and whether scheduler differences actually change goals. If the head-to-head is promising, the next gate is a **live RLBot capture trace** of timestamp, kickoff-pause flag, ball coordinates, Nexto kickoff_index and active controls, aligned against identical RocketSim states (ideally saved match-state snapshots). Only after measuring remaining differences should a new PPO continuation against the improved opponent be considered.
