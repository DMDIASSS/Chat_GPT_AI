# Nexto round benchmark

This is a separate, inference-only benchmark. Import
`STUDIO_NEXTO_ROUNDS_1_TO_400.json` into Studio's **All settings → Import settings**.
In **Training**, click **Build engine** once after installing this source update.
Then **Find best models → Nexto rounds preset (40) → Start comparison**.
The preset button changes comparison settings while retaining training settings. Normal comparison buttons automatically
use the benchmark when `selector.goal_race` is configured. **Resume comparison**
continues the exact saved benchmark. **Pause active job safely** finishes active
rounds, saves their results, and stops scheduling. **Results → Refresh reports**
shows the top 20 in each format. `winrates.csv` and `goal_benchmark.json` contain all
checkpoints, aliases, real W/D/L, observed/assigned win rates and per-color counts.
No playing model, original checkpoint or existing comparison is overwritten.

## Rules

- Only Nexto opponents; every candidate supplies its whole squad in 1v1, 2v2, 3v3.
- 40 rounds per checkpoint per format by default; choose an even budget 30–50.
- Each round starts at kickoff and ends at the **first goal**, or a draw after
  90 simulated seconds without a goal. A timeout draw counts as one round.
- Colors run in matched pairs with the same seed. Fresh pairs use new seeds;
  every checkpoint shares that seed schedule. Deterministic greedy policies.
- Scripted kickoff is **ON for all cars** in the provided preset, including the
  candidate squad and Nexto. This assesses play after kickoff, not learned kickoff.
- Default early-stop threshold: 10 consecutive wins, losses or draws; adjustable
  from 8 to 12. Check the streak in planned seed/color order after each full color
  pair, independent of which native arena finishes first. This can finish one
  additional round after the threshold is crossed.
- The streak ends **only that checkpoint's affected format**. Other formats and
  checkpoints continue. AUTO WIN assigns 100%; AUTO LOSS assigns 0%; AUTO DRAW
  assigns a draw, with no fabricated win percentage. Measured counts remain intact.
- **Observed win rate = W / (W + D + L)**. Decisive win rate = W / (W + L).
  JSON also includes draw rate and points rate `(W + 0.5 D) / rounds`.
  An all-draw matchup has observed 0% wins, 100% draws, and AUTO DRAW.

These are first-goal **round** win rates, not five-minute match win rates. Ten
consecutive results justify the configured stopping heuristic, not proof of a
true 100% or 0% long-run win probability. Auto-assignment can disagree with the
observed percentage if earlier rounds had different outcomes. Reports keep both.
The benchmark is descriptive; it neither certifies the best model nor promotes it.

## Settings and budgets

Under **All settings → selector → goal_race**:

```json
{
  "rounds_per_format": 40,
  "timeout_seconds": 90,
  "early_stop_streak": 10,
  "seed_base": 881000000,
  "formats": ["1v1", "2v2", "3v3"]
}
```

Checkpoint paths come from `selector.families`. The preset discovers only
`data/isolated/mechanics_curriculum/selected7_mechanics01/update_*.pt`, including
new updates past 400 if present, plus required update180. Accepted copies are
not scanned separately. Exact actor-weight duplicates share evaluations, retaining
all source aliases. Nexto is the sole rival; no update180 opponent or extra
baseline matches are added to statistical results.

`worlds: 8` batches inference and simulation; increase only after measuring GPU
memory and actual throughput. `job_group: 128` is scheduling size, not concurrent
worlds. At 400 distinct policies, the full budget is **48,000 rounds** before
streak savings. This is substantially longer than the previous 1,608-game
20-second screen. Passive formats stop after about ten draws; close mixed
matchups can use all forty rounds. No fixed wall-clock completion time is promised.

Game budget this launch is 100,000 in the preset, enough for all 400 models.
Reducing it pauses at the launch budget; resume to finish. **Stop after stage**
is ignored in this benchmark; it has its own round/streak completion rules.
The run is `nexto_rounds400_01`; change it for a fresh benchmark. Settings, native
binary, source actors and runtime are pinned. Rebuilding/editing code invalidates
older run resumes; preserve those reports and start a new run instead.

Reports are under:
`data/isolated/model_selection/runs/nexto_rounds400_01/`.
Round plans and completed native records are retained. Resume rebuilds statistics
from the ledger and verifies recorded file hashes, without replaying committed
rounds. Abrupt interruption replays only unfinished rounds; a pause drains active
rounds. No model weights are changed and no full-model downloads are needed.

## Validation

Python tests cover streak ordering, all-draw accounting, per-format isolation,
observed versus assigned statistics, budgets, resume without duplicate rounds,
cache tamper rejection and existing selector/Studio compatibility. The native
integration tests exercise real RocketSim first-goal termination and no-goal
timeouts, full candidate squads and immutable cache reuse. Cloud tests use public
Nexto fixtures; the user's private checkpoints and Windows/CUDA launches must be
validated locally. Install the source ZIP, rebuild the engine, and use a fresh run.

Validated on the cloud Linux/CPU instance: 59 targeted tests passed and one
Windows-only CMD invocation test was skipped. A separate real native-controller
fixture completed 48 rounds over two distinct public-fixture actors, all three
formats and both colors, with launch-budget pause/resume, unchanged source hashes
and no duplicate completed rounds. Its timeout was intentionally 0.1 seconds
to test the controller quickly; it does not establish model quality. The native
first-goal integration also used 90-second rounds and verified actual goals
against a deliberately zero-weight fixture, early termination, timed draws and
cache reuse. No private user checkpoints were benchmarked in cloud.
