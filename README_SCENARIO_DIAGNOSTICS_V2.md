# Chat_GPT_AI — Scenario Diagnostics v2: kickoff-quality evaluation

This is an **update to Scenario Diagnostics v1**, not an AI training script. It
keeps the original *first-goal / time-cap result* and adds a separate kickoff
assessment based on the player's desired rules.

## Installation

1. **Pause the AFK trainer** and stop all other AutoLeague/diagnostic processes.
   Wait for the training process to exit at a saved checkpoint. Don't delete
   `.training.lock`: it is an active OS lock held by a running process.
2. Unzip the archive into `E:\Downloads\Chat_GPT_AI`, at the same level as
   `auto_league.py` and your `.venv` folder. Allow overwriting the two existing
   `rl_*.py` diagnostic files and existing `RL_DIAG_*.bat` launchers.
3. Double-click `RL_DIAG_0_CHECK.bat` to verify the checkpoint paths and hashes.
4. Double-click `RL_DIAG_1_SMOKE.bat` to test RocketSim compatibility on your PC.
5. Double-click **`RL_DIAG_4_KICKOFF_QUALITY.bat`** to run the dedicated kickoff
   benchmark. Alternatively, `RL_DIAG_2_BENCHMARK.bat` still tests all five
   gameplay scenario types and now includes the kickoff-quality metrics too.
6. Share the new `data\scenario_diagnostics\scenario_diagnostics_v2_*.json` report.

All models are **read only**: the evaluation never trains, promotes or replaces
champion/candidate/backup weights. A running main AutoLeague may cause a safety
lock failure until you pause it.

## What counts as a kickoff success?

The evaluator compares two cars, A and B, in 1v1 games. It observes a snapshot
**4 simulated seconds after kickoff (60 decisions)** and gives an early goal
precedence through **6 seconds (90 decisions)**.

1. **Ball advantage:** the car is no more than **1400 Unreal units** from the
   ball *and* at least **150 units closer** than the opponent. This attempts
   to measure useful post-kickoff ball access, not just ball speed.
2. **Early goal:** scoring within 6 simulated seconds immediately counts as
   success for the scoring car and failure for the other, overriding the
   4-second snapshot. A goal after 6 seconds can win the ordinary first-goal
   match, but no longer gets labelled a kickoff goal.
3. **Safe boost pickup:** estimated boost gained during the first 4 seconds is
   >=10; at the snapshot the car still has >=30 boost; **and** the danger
   heuristic does not find the ball close to the player's own goal or driving
   rapidly towards it with the opponent better positioned.

A boost pickup is estimated from positive *net* changes of the car's boost
quantity over each 8-physics-tick step. It's a **conservative approximation**:
a pad pickup that is immediately spent in the same interval might not register.
Danger is a **heuristic**, not a calibrated predicted-goal probability. The
possession and safety thresholds are initial hypotheses to tune using watching
replays or simulator recordings.

For the combined kickoff-quality label:

| Outcome | Meaning | Quality score for model A |
|---|---|---|
| `ours` | A qualifies, B doesn't (or A scores within 6s) | 1 |
| `nexto` | B qualifies, A doesn't (or B scores within 6s) | 0 |
| `contested` | Both qualify through ball / safe boost criteria | 0.5 |
| `neutral` | Neither qualifies | 0.5 |

The JSON also reports per-player *success rates* and counts of qualifying
reasons (`ball_control`, `safe_boost_pickup`, `early_goal`). Those success rates
**do not need to sum to 100%**, since both players can collect boost safely.

## Running a targeted kickoff benchmark

`RL_DIAG_4_KICKOFF_QUALITY.bat` runs **40 matched seed pairs per matchup**,
with each pair playing once from each side, 90 decisions maximum per episode.
It tests three native-compatible models against original Nexto, all three
head-to-head matchups, and original Nexto against itself as a control.

For a shorter custom run:

```bat
.venv\Scripts\python.exe -u rl_scenario_diagnostics.py --kickoff-only --pairs 8 --decisions 90 --control-pairs 3
```

For full scenario analysis, run `RL_DIAG_2_BENCHMARK.bat`; kickoff quality remains
independent of the later first-goal W/L/D. Pair results cache in
`data\scenario_diagnostics\paired_runs_cache_v2.jsonl` and survive Ctrl+C
once completed; running the same command resumes from cached pairs.

Example JSON locations:

- `results.champion__vs__original_nexto.by_scenario.kickoff`: original
  first-goal score (possibly after kickoff)
- `results.champion__vs__original_nexto.kickoff_quality`: new kickoff status,
  success rates, confidence interval, and reasons
- `results.cycle09__vs__original_nexto.kickoff_quality`: Cycle 9's kickoff scores

## Interpretation and limitations

- This is a 1v1 **RocketSim** simulation, not a measurement of five-minute
  Rocket League ranked-game win rate.
- A close ball is not necessarily good possession, and having boost does not
  guarantee defensive safety. Watch actual play before tuning rewards.
- Early goals override prior positional advantage to avoid contradictory labels.
- The report includes first-goal outcomes **separately** so historical
  comparisons remain meaningful; the added kickoff-quality metrics cannot
  be compared numerically with prior first-goal-only tournament results.
- The uncertainty bands are exploratory, especially for models selected after
  prior tournaments. No checkpoint promotion is automated.
- Simulation still needs testing on your local Windows machine with your
  RocketSim and PyTorch dependencies. Pure-Python unit/mocked tests are in
  `tests/` but no full simulator is available in the build environment.

## After you send the results

We can find out whether Cycle 9, Wavedash, or the current champion is best at
ball access vs safer boost collecting and whether winning kickoffs correlates
with later scoring. This will guide the next PPO reward/curriculum experiment
without endangering the champion.
