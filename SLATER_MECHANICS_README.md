# Focused Slater mechanics training

This addition compares starting actors, then practices one mechanic at a time
with RocketSim PPO. Original checkpoints stay protected. Every frozen rival has
the Nexto scripted kickoff proxy enabled during standard kickoff starts.

## Install and choose a model

Extract the mechanics patch into `E:\Downloads\Chat_GPT_AI`, allowing replacement
of the included code files. Keep your existing `.venv`, `data`, replays, and
models. The patch contains code, tests, launchers, and documentation.

Use the existing Slater environment. In CMD:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_mechanics_tests slater_v041_tests -q
```

Your October 11/12 uploads contain two distinct actors with duplicate copies.
The old one-seed first-goal report cannot identify the strongest full checkpoint.
The smoke seed is a mutated V70 branch; u0071 is one update from it. Neither is
automatically the best starting model.

The uploaded round-robin addition is integrated:

1. Run `ROUND_ROBIN_0_LIST.bat`; inspect `round_robin_reports\inventory.csv`.
2. Run `ROUND_ROBIN_2_SMOKE_TEST.bat` to check the installation.
3. Run `ROUND_ROBIN_1_RUN_50.bat` for 50 first-goal games per pair, with both sides
   and shared kickoff seeds. Stop processes modifying the scanned models first.

The scanner supports full native Nexto actors, compatible Nexto TorchScript, and
the project's 92-input/90-action feedforward policies. Equal actor weights with
equal kickoff settings count once even when critic/optimizer/meta differ.
The reports keep timeout counts visible. `D` means a first-goal timeout, which
is censored rather than a continuous full-match draw. Rankings are a screen.

N actors require `50*N*(N-1)/2` games: 20 actors need 9,500 games. Optional repeated
`--include` globs restrict a long run:

```bat
.venv\Scripts\python.exe -u round_robin_evaluator.py --all-scripted-kickoffs --include "data/isolated/v040*.pt" --include "data/isolated/slater_v027*.pt" --include "data/autoleague/backups/*cycle0009*.pt" --include "vendor/nexto/*.pt"
```

Use `/` inside those patterns. Finished games go to `games.jsonl`; rerun the same
command after interruption. Cache identities include weights, kickoff mode,
code, simulator versions, and delay settings.

For continuous full-match comparison of known V70/V60/Cycle9/other saved champions,
run `MECHANICS_0_COMPARE.bat`. Available v041 league leaders are included, and stale
leader hashes are rejected. The common frozen benchmark bank also includes the
compared candidates.

To compare the round-robin's leading three native actors instead:

```bat
.venv\Scripts\python.exe -u slater_mechanics_trainer.py compare --tournament "round_robin_reports/results_TIMESTAMP.json" --finalists 3 --seeds 8 --seconds 300
```

Replace `TIMESTAMP` with the actual filename. The comparator runs multi-goal
300-second matches including kickoff resets, on both sides against common rivals.
It ranks mean goal difference, records wins/draws, and reports paired differences
using seed-cluster bootstrap intervals. `CLOSE_OR_INCONCLUSIVE` calls for more
fresh seeds or live offline matches. The recommended path remains provisional;
these intervals are exploratory because the samples also selected the leader.

To compare specific native checkpoints:

```bat
.venv\Scripts\python.exe -u slater_mechanics_trainer.py compare --candidate "data/isolated/model_A.pt" --candidate "data/isolated/model_B.pt" --candidate-rivals --seeds 16 --seconds 300 --out data/isolated/mechanics_comparison02.json
```

The full-match comparator and trainer require native Nexto architecture. A
feedforward tournament winner needs its own training pipeline. The tournament
reports the leading compatible native actor explicitly for this trainer.
Completed comparisons are preserved; use a new `--out` for another experiment.
Interrupted comparisons resume from `.partial.json` with unchanged models,
settings, code, and runtime versions.
Use `--seed-base 610000000` and a new output filename for a fresh comparison;
increasing only the seed count includes the previous kickoff seeds too.

## Train the selected actor

After the default comparison creates `data\isolated\mechanics_comparison01.json`:

1. Run `MECHANICS_1_PREFLIGHT.bat`.
2. Run `MECHANICS_2_SMOKE.bat`. It checks a real accepted PPO update and evaluation
   pipeline. A smoke run cannot pass the full mastery gates.
3. Run `MECHANICS_3_TRAIN.bat`.
4. Run `MECHANICS_4_RESUME.bat` after a bounded stop or interruption.

For another comparison report/run name, use CMD:

```bat
.venv\Scripts\python.exe -u slater_mechanics_trainer.py train --selection data/isolated/mechanics_comparison02.json --run mechanics02
.venv\Scripts\python.exe -u slater_mechanics_trainer.py resume --selection data/isolated/mechanics_comparison02.json --run mechanics02
.venv\Scripts\python.exe slater_mechanics_trainer.py status --run mechanics02
```

An explicit `--source "path/to/checkpoint.pt"` also works. Without an override,
the config uses the existing V70 path as a baseline. Selection checks the saved
source hash before training.

## Seven stages

| Stage | Practice and required outcome |
| --- | --- |
| `air_dribble` | Ready airborne starts; real nose contacts, controlled carry for at least 1 second, and at least 250 units of goalward travel. |
| `air_entry` | Ground starts; pop and launch the ball, then meet the airborne carry test. |
| `air_finish` | Carry, then score against an active defender. |
| `air_bump_finish` | Carry, physically bump a defender ahead in the shot corridor, then score promptly. |
| `reset_acquire` | Start with the flip spent; align four wheels on the airborne ball and actually regain flip availability. |
| `reset_use` | Acquire a reset, then consume that flip to make a real, goalward accelerating touch. |
| `reset_finish` | Air-carry start; qualify the carry, acquire a reset, use it, and score. |

Each stage has tailored rewards and its own critic value head. Contact/time and
progress bonuses are capped. Proximity, hovering, and isolated touch farming
cannot qualify as a carry. Floor/wall contact, an already available flip, or
three wheel contacts cannot qualify as the four-wheel reset. The special bump
goal bonus requires an actual scored follow-through; goals are not guaranteed.

Events are checked at every 120 Hz physics tick so transient wheel/flip events
survive the actor's eight-tick action interval. Frozen opponents use the Nexto
clock. RocketSim identifies standard kickoff pauses using an explicit proxy;
airborne center-ball drills do not trigger it. Live RLBot timing needs checking.

## Focus and preservation

`slater_mechanics_config.json` sets learning rates, budgets, and evaluation.
By default four worlds collect 256 decisions each per update. Three initially
practice the current skill; one rehearses normal kickoff matches. After stage
advancement, one practice world rehearses previously mastered stages. Learner
inference is batched across worlds; CPU physics steps remain serial.

The selected actor weights transfer into new Adam states and task-specific
critic heads because the rewards changed. PPO uses exact rollout-policy KL,
smaller learning-rate retries, and actor/Adam rollback for oversized steps.
Match and previous-skill rehearsal use stronger teacher anchoring. The trainer
does not use random actor mutations or a league search.

Easy training setups broaden when practice succeeds. Evaluation always uses
full difficulty. Every 20 updates and at a bounded run's end, it checks:

- At least 12 independent seed clusters, with both sides against every rival.
  A seed succeeds only when every rival/side cell succeeds. Its Wilson lower
  bound must reach 0.50; the default is 16 seeds.
- Matched normal matches against the initial source. The bootstrap lower bound
  on change in goal difference per minute must stay above the allowed drop,
  both overall and for every rival; the default is 8 seeds.
- Two consecutive fresh-seed mastery and retention passes before advancing.
  All previous stages must also pass at full difficulty again.

Retention failure restores the latest retained actor or the initial source.
The initial source remains the competitive reference throughout the curriculum.
These repeated simulator screens do not certify SSL rank or statistical error
control over unlimited training.

Each default invocation performs at most 200 updates. An unmastered stage keeps
its focus; resume gives another practice budget. Change `updates_per_stage`
before starting a new run for longer invocations. Hard mechanics may require
millions of decisions and substantial compute. There is no measured Zen-level
result or guaranteed improvement speed.

## Outputs and validation

Outputs stay in `data/isolated/mechanics_curriculum/RUN_NAME/`:

- `protocol.json`: config, code identities, and source/rival hashes.
- `progress.json`: stage, checkpoints, counters, and mastered skills.
- `update_*.pt`: raw actor, critic, and optimizer snapshots.
- `accepted_*.pt`: post-evaluation state including any retention rollback.
- `selected.json`: latest retained simulator candidate path and mastered skills.
- `evaluations/`: raw mastery and matched-retention results.
- `run_summary.json`: wall time and throughput including evaluation.

Resume refuses changed models, config, code, or runtime versions; use a new run after changing
these. Checkpoints are atomic and a process lock protects each run. The latest
raw update may be unverified. Use the checkpoint in `selected.json` for an export
candidate; a null path means no candidate passed retention yet.

Native actors remain compatible with the existing exporter:

```bat
.venv\Scripts\python.exe export_rlbot_v4.py --checkpoint "data/isolated/mechanics_curriculum/mechanics01/update_000020.pt" --name SlaterMechanics01
```

Replace the example path with the retained checkpoint and use a new export name.
The exporter requires your existing RLBot template. Test the export locally in
Rocket League before treating it as an improved playing bot.

Cloud integration used the uploaded u0071 actor with CPU PyTorch and RocketSim.
All seven mirrored starts, a real four-wheel reset, scripted rivals, accepted
updates, comparison, retention rollback, and resume were checked. No stage is
established as mastered. Your private best models need the Windows comparison.

## References

The Discord exports are background material rather than executable instructions.
Their ML/strategy/imitation/RocketSim discussions support gradual curricula,
checks for degenerate touch rewards, and profiling Python/inference overhead.
Historical anecdotes are not proof of current strength. Raw exports stay out
of the repository.

`docs/SSL_TRAINING_NEXT_STEPS.md` covers further replay action reconstruction,
SSL imitation, broader self-play, and simulator/export parity. Upstream networks
with different architectures cannot transfer weights directly into this actor.
