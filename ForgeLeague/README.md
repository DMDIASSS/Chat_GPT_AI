# ForgeLeague 0.1 — two independent trainable bots

This is a separate experiment. It trains the controls of a Chronos-family bot and a Galactus V2-family bot. It does not train the Triad selector. Existing NovaForge, Fusion and selector runs are preserved. Both new learners use Octane, as requested.

## Start on your Windows laptop

1. Pause every existing trainer and wait for it to save. Close other viewers.
2. Unzip the download. Copy its **novaforge**, **triadbot** and **forgeleague** folders from inside `chat_gpt_ai` into your existing `Chat_GPT_AI`. Replace program files; keep your `.venv`, `assets`, `runs`, `exports` and `rlviser.exe`. Do not create a second nested `Chat_GPT_AI` folder.
3. Open `forgeleague/0_CHECK.bat`. It must end with `FORGE_CHECK_PASS`. This uses NovaForge's existing Python 3.11 environment; no new packages are required. For a fresh installation, run NovaForge's setup first.
4. Open `1_CREATE.bat` once. It creates the new `duel01` run. It copies the exact hash-verified frozen Fusion used by `selector06`, otherwise `selector04`, into the Chronos-family initialization when available. Otherwise it explicitly reports original Chronos. Galactus starts from the pinned Galactus V2 actor. A broken existing Fusion asset is an error, never a silent fallback. Nothing is taken from an unverified latest candidate.
5. Open `2_START_OR_RESUME.bat` and leave that console open. It uses your saved W&B login through the SDK. No key is searched for, printed or put in an archive. If online login fails, fix it with NovaForge's W&B setup or use the offline command below.
6. Pause with `3_PAUSE.bat`; wait for the training console to print `FORGE_REPORT`. During training, stopping happens after a complete rollout. During evaluation it stops promptly. Ctrl+C also pauses; an incomplete rollout is discarded and the last complete checkpoint remains resumable.
7. Use `4_REPORT.bat` and send the newest ZIP from `forgeleague/reports`. After the first pilot, use `5_EXPORT_RETAINED_BOTH_V5.bat` or the automatic exports in `forgeleague/exports/duel01`.

Allow several GB of free disk space; reserve at least 15 GB for a long run. Intermediate checkpoints are pruned, but final checkpoints and the frozen actors needed to reproduce historical tasks remain. This is one serial trainer, not ten trainers competing for the laptop's RAM. Do not run Fusion or Triad training simultaneously.

## What happens automatically

| Phase | Work | Default learner budget |
|---|---|---|
| Critic pilot, once | Ordinary vs privileged critic, separately for each family, same initial actor and training seed | 8,192 decisions per arm; 32,768 total |
| Pilot evaluation | Compare the two arms with blind actors, then the chosen arm against its retained parent | Paired timed matches; extra fresh confirmation only for an apparent improvement |
| Main league | Continue each family's own optimizer against a pool frozen for that block | 32,768 decisions per family |
| Challenger bank | Train one curriculum specialist per family, then freeze both | 8,192 decisions per specialist |
| Repeat | Rebuild the pool from retained mains, historical challengers and original bots | Two main blocks and two specialists per cycle |

The first two rollout updates of each fresh model train only its critic. The ordinary critic wins uncertain pilot comparisons. A single training seed is a local pilot, not proof that a method generalizes across seeds.

Four challenger curricula rotate over successive cycles: **pressure, defense, recovery, full match**. After four cycles there are four recent challengers per family. These are curriculum specializations, not guaranteed personality labels. We did not add a demo bonus or claim a demochasing specialist: useful demos should first be measured through resulting goals and match outcomes.

The pool includes each family's frozen retained main (snapshot self-play), the other main, original Chronos/Galactus/Nexto, and completed challengers. Opponents never change weights during a block. Harder opponents receive more sampling weight using measured losses and conceded-goal share, with a 50% uniform mixture and bounded weight ratios. This changes practice frequency, not the value of goals. Missing evidence gets a neutral weight. Frozen challengers are training adversaries; they cannot become exported champions without a separate guard evaluation.

This first version deliberately tests a small system before adding counterfactual rollouts, replay-state mining, automatic reward search, more expert adapters, or team coordination. Those are later research choices, not advertised features.

## What the networks learn

The pretrained Chronos 225-feature and Galactus 258-feature networks both remain trainable. Galactus keeps its ball forecast features. A small bounded residual receives ordinary game features plus score difference, remaining match time and a centered/stationary-ball flag. Its final layer starts at zero, so the initialization reproduces the pretrained core's logits exactly.

The optional privileged critic receives the opponent's **already queued** eight controller values and the delay until application. The opponent chooses those before the learner chooses its current action. The same prepared command is actually executed; no speculative future trajectory or second opponent query is used. The actor does not receive these nine values. It is evaluated and exported independently of the critic. This is asymmetric actor-critic training, not opponent mind reading in RLBot.

Reward version `timed-match-goal-potential-v1`:

```
10 * goals_scored_minus_conceded_this_step
+ 10 * sign(final_match_score_difference)  # match end only
+ gamma * Phi(next_state) - Phi(current_state)

Phi = 0.35 * team_relative_ball_y / 5120
      - 0.10 * min(car_ball_distance, 12000) / 6000
```

A finite match ends with zero terminal potential and no value bootstrap. Goals continue into a new kickoff in the same match. The discounted shaping sum telescopes, so it cannot pay indefinitely for circling or touching the ball. There are no standalone touch, boost-use, height, reward-diversity or controller-usage bonuses. The base goal and match objective still requires empirical validation; no reward formula guarantees a strong bot.

Default training matches last 60 simulated seconds. Goals have no replay pause. A decision uses seven ticks of held controls, then the newly chosen command; RocketSim adds its one-tick input delay. After an early goal, the unused portion of that decision is counted as dead time. These approximations and inherited native-adapter limitations make simulator results different from live RLBot matches.

## Champion protection and diagnostics

Every main block gets paired W/D/L against its retained champion, on both colors and the same starting seeds, against a fixed panel: initial Chronos-family parent, initial Galactus-family parent, and Nexto. Default screening uses four seed pairs per opponent, 60 seconds per game. An approximate stratified 99% paired interval, minimum gain and per-opponent tolerance must pass. An apparent gain gets eight **new** seed pairs per opponent for confirmation. Only a confirmed improvement changes that family's champion pointer. There is no forced controller diversity or averaging of unrelated network weights.

A substantial measured regression stops the league and preserves the candidate for diagnosis. Three successive PPO updates outside the frozen-anchor KL limit also halt it. Promotion checks are practical safeguards, not a lifetime statistical guarantee under repeated adaptive testing. If the evidence stays uncertain, the candidate can continue learning while the retained export stays unchanged. The KL anchor can move after a verified promotion; original parents remain fixed references.

`8_FINAL_HELDOUT_TEST.bat` is a separate, longer test: 300-second games, fresh seeds, both colors, and original Chronos/Galactus/Nexto/Ripple. It never promotes a bot. Use it after pausing and before treating a training-chart gain as a final result. Repeatedly tuning on this test would make it a development set.

W&B records per-family PPO losses/KL, goals, concessions, critic mode, paired evaluation gains and task decisions per second. `trainer/timesteps` counts completed training decisions across tasks. Evaluation decisions are not counted as training. CSV files, reward configuration, exact task recipes, source hashes, checkpoint hashes, lineage and W/D/L trials also stay local and are included in reports. Higher SPS is useful only alongside better held-out play.

Checkpoints include the full policy, frozen anchor, critic, optimizer, warmup/update counters and RNG state. Resume starts a deterministically seeded new match at the last complete checkpoint. It does not promise bitwise continuation of RocketSim's internal contact state. Each resume records its current source hashes. Run configurations are immutable; change an objective or budget by creating a new experiment.

## Exports and watching

`5_EXPORT_RETAINED_BOTH_V5.bat` writes **two independent bots**, each with `actor.lt`, identical `actor.pt`, metadata, an Octane loadout and RLBot v5 TOMLs. On the same PC import **bot.bot.toml** directly. On another PC run the export's **INSTALL.bat**, then import **bot.portable.bot.toml**. `DIAGNOSE.bat` checks model loading and `startup.log` records startup errors.

The actor is one complete TorchScript archive. It needs the bundled loader and observation contract; it is not a drop-in replacement for another bot's split `POLICY.lt` and `SHARED_HEAD.lt`. TOML describes a launcher, not neural weights. No critic or private opponent input is exported. The SDK uses its Hivemind connection class, but this implementation supports **1v1 only**, not a coordinated team.

`6_WATCH_CHRONOS.bat` and `7_WATCH_GALACTUS.bat` show retained champions. Blue/car 1 is your bot; orange is the original opponent. The existing checked RLViser launcher finds `Chat_GPT_AI/rlviser.exe` and uses ballcam, FOV 110, distance 270, height 100, pitch -4, no added shake. Only one viewer can run at a time.

Exports happen automatically after the pilot and every completed league cycle, with actor and source hashes in their folder name. A retained initialization may be exported when no improvement has passed: check the champion JSON/report rather than interpreting the file's existence as a new best bot.

## Useful commands

Run these from `forgeleague` with the installed NovaForge Python:

```bat
..\novaforge\.venv\Scripts\python.exe -u run.py train --run duel01 --wandb offline
..\novaforge\.venv\Scripts\python.exe -u run.py train --run duel01 --wandb off --once
..\novaforge\.venv\Scripts\python.exe -u run.py create --run duel02 --config my_experiment.json
..\novaforge\.venv\Scripts\python.exe -u run.py fork --source duel01 --run duel02 --config my_experiment.json
```

`--once` finishes the current pilot or league cycle. A fork copies **both retained actors exactly**, resets the critics/optimizers, and runs the pilot again; it never replaces the source run. To recover from a protection stop, preserve its report, inspect the evidence, then use a new experiment name rather than deleting the halt reason or overwriting the better actor. The default BAT launchers target `duel01`; use commands for other names.

The longer plan and validation evidence are in NovaForge's `FORGELEAGUE_v0.1.md`.
