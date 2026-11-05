# Research stages 1–2: measured improvements before automatic tuning

This release adds experiment infrastructure. It does not claim a stronger model,
an optimal reward, autonomous objective discovery, or one million decisions/sec.
Existing expert weights, selector architecture, option duration and export
formats are preserved. The default objective has identical coefficients to v1.8.1.

## Findings from the uploaded reports

| Policy | W / D / L | Goals | Comparator |
| --- | --- | --- | --- |
| Random Triad | 4 / 3 / 9 | 20:36 | Original Chronos: 10 / 3 / 3, 41:16 |
| Learned selector, 179,714 decisions | 11 / 4 / 1 | 42:10 | Chronos-only initial routing: 12 / 2 / 2, 43:11 |

Random switching was worse on its tested seeds. The learned selector had equal
signed match points to its initialization. Its paired mean difference was zero;
the zero reported block standard error reflects cancellation within these eight
sampled color-paired blocks, not proof of equivalent policies. This does not
establish an improvement over the earlier 43k candidate or original Chronos.
The tests used different seed banks, so do not directly compare random-vs-learned
totals. All matched candidate/baseline starts in the uploads have equal hashes.

The unchanged initial baseline varied slightly between the user's earlier and
current reports. Three local repeats of one 60-second Chronos matchup produced
the same score/touches, but that does not establish universal determinism.
Upstream RocketSim calls automatic respawn with an unseeded random source after
a demolition. The installed binding exposes seeded manual respawn/reset_kickoff,
but no global seed for automatic respawns. We preserve match rules and record this
limitation instead of disabling demos or claiming exact deterministic matches.
Cross-platform floating-point behavior is another reproducibility limit.

## Use the update

1. Pause selector training with **8**, wait for it to save, and close an older
   evaluation console before replacing source files.
2. Copy `chat_gpt_ai/novaforge` and `chat_gpt_ai/triadbot` from the ZIP into your
   existing `Chat_GPT_AI` folder. Select Replace for program files. Keep your
   `.venv`, `assets`, `runs` and `exports`. No dependency reinstall is needed.
3. In `triadbot`, run **10_BACKUP_SELECTOR.bat**. It retains full.zip, the latest,
   initial and champion actors, their metadata, configuration and guard state.
4. Run **11_VALIDATE_SELECTOR.bat**. It compares latest against initialization
   on a separate validation seed bank: 32 games per policy, 64 games total,
   each 60 simulated seconds. Allow every game to finish.
5. Run **12_RESEARCH_REPORT.bat** and share the generated ZIP. It includes
   objective definitions, results, guard/status and selected provenance; no
   model weights or raw logs. Until that result is reviewed, keep the current
   champion and the old 43k backup. Fusion stays paused.

Launcher 7 remains a development comparison, using its previous seed bank.
Launcher 4 resumes selector01; 5 watches latest; 6 exports champion. Training
still runs until paused or halted by the existing regression guard. A manual
evaluation does not promote or stop training. Backups are not pruned automatically.

Every completed manual evaluation creates a new folder under
`triadbot/runs/<run>/evaluations/` containing the tested actors, full checkpoint
if present, config, result and evaluation manifest. `wdl.json` is a convenience
copy of the newest result. Expect a few MB per archived evaluation. Source is
stored once per source hash under `research/source`. Interrupted evaluation
keeps prior complete results and leaves the live weights unchanged.

## Objectives and experiment identity

`nova/objectives.py` registers three bounded, versioned definitions:

| Name | Goal coefficient | Field potential | Distance potential |
| --- | --- | --- | --- |
| current | 10 | .35 | .1 |
| field_only | 10 | .35 | 0 |
| goals_only | 10 | 0 | 0 |

At each eight-tick decision: `r = goal*outcome + gamma*Phi(next)-Phi(old)`.
`Phi = field*team_relative_ball_y/5120 - distance*min(car_ball_distance,12000)/6000`.
True terminal potential is zero. Time-limit truncation retains potential for
value bootstrapping. These are hypotheses to test; removing distance could help
or hurt. No teacher's original hidden reward is recovered by copying actions.

Training saves an immutable `experiment.json` with the objective definition and
config. Later config changes require an isolated fork. Each session records
source hashes, an exact source ZIP, teacher lock hash, installed versions, Python,
platform, starting step and session seed. Each session writes a separate CSV log to preserve
previous sessions. The provenance manifest records the effective selector PPO
settings separately from the inherited Chronos PPO config. W&B receives the objective through the
run config and now logs `selector/chronos_fraction`, `selector/galactus_fraction`,
and `selector/ripple_fraction` over the rolling completed-episode window.
Manual W/D/L reports also record expert decision counts during the comparison.

Resume preserves policy, optimizer and timesteps. It starts a fresh rollout and
seeds it with `(selector_seed + checkpoint_timesteps) mod 2^32`; it is not an exact
continuation of the previous physics/RNG state. Keep interruption schedules equal
when comparing runs. Forks retain the source critic/optimizer, so a changed
objective needs value adaptation. This release does not promise deterministic RL.

## Controlled pilot, after validating the current selector

The versioned protocol is `configs/selector_research_v1.json`. Freeze one source
checkpoint and create all three variants before training any of them. In a CMD
opened in `triadbot`, these commands create separate runs and leave selector01
untouched:

```bat
..\novaforge\.venv\Scripts\python.exe run.py research-fork --source selector01 --run pilot_control --objective current --seed 271
..\novaforge\.venv\Scripts\python.exe run.py research-fork --source selector01 --run pilot_field --objective field_only --seed 271
..\novaforge\.venv\Scripts\python.exe run.py research-fork --source selector01 --run pilot_goals --objective goals_only --seed 271
```

For each run, replace `pilot_control` below with its name. Use one process at a
time on this laptop. Run the training command once per variant; it adds 32,768
decisions to its source checkpoint, then saves and exits. If interrupted, use
selector-status to calculate the remaining budget before resuming. PPO rounds
complete training rollouts to multiples of 512 decisions.

```bat
..\novaforge\.venv\Scripts\python.exe run.py selector-train --run pilot_control --steps 32768 --once
..\novaforge\.venv\Scripts\python.exe run.py selector-evaluate --run pilot_control --split development --pairs 2 --seconds 60
..\novaforge\.venv\Scripts\python.exe run.py research-report --run pilot_control
```

Do not rank reward totals across these variants: they use different objectives.
Compare matched W/D/L and goals against the same frozen opponents. A 32k pilot
can reject obvious failures; it cannot prove long-run improvement. Confirm a
promising variant with fresh validation starts and independent training seeds
811 and 1601, with equal budgets and initialization. Use the test bank only after
selecting the variant, for example `--split test --pairs 8`. Reusing a bank is
flagged in its manifest; once inspected, it is no longer an untouched test.
The split labels separate evaluation starts; training seeds are independently
specified and do not make native automatic respawns deterministic.

## Staged plan and decisions

1. **Architecture audit, done:** selector chooses among three frozen native-control
   experts; PPO trains the 234-input gate. Chronos/Fusion use a separate actor.
   Confirmed integration points: ChronosArena potential/decision rewards,
   selector session startup, native runner, timed match suite and checkpoint export.
2. **Registry/tracking/evaluation foundation, implemented:** bounded registry,
   isolated forks, immutable config and source records, checkpoint backups,
   split seed banks, archived tested models/results, and expert-use measurements.
   Local short integration tests validate execution, not competitive strength.
   Next decision: does fresh validation support continuing the current selector?
3. **Combination search/ablation, protocol prepared:** the three-arm pilot above.
   Next decision: is any effect consistent across opponents, seeds and budgets?
   Remove failures and keep a control branch. More objectives require a reason.
4. **Automatic adjustment, not implemented:** only after useful objective effects
   are replicated. Adjust bounded coefficients between isolated runs, log every
   change, keep the scoring test independent, and retain the existing champion.
5. **Discovery/counterfactuals, not implemented:** first measure expert disagreement
   and transfer fidelity. Branching the complete simulator and expert hidden state
   is not verified; no counterfactual rollout capability is claimed.
6. **Autonomous prioritization, not implemented:** use measured improvement per
   wall-clock budget once repeated trials provide reliable estimates. Avoid
   selecting winners from the same repeatedly inspected test bank.
7. **Controlled comparisons, pending real training:** run matched experiments,
   repeat promising cases and report negative results alongside positive ones.
8. **Main-bot integration, gated:** require development, fresh confirmation and a
   final held-out comparison. Forks cannot overwrite source runs. Existing
   champion retention and substantial-regression stopping remain active.

Parallel simulation already exists for Chronos PPO. The selector currently uses
one worker; three-model inference can dominate laptop throughput. Measure learning
per wall-clock time before adding workers. This release adds no native GigaLearn
backend or speed/strength guarantee. A fixed live car keeps one hitbox while
switching experts; Ripple timing/queue transfer limitations still apply.
