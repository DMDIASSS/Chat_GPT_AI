# Replay model to simulation learning: a separate hybrid run

This branch uses the trained RVQ replay model as its starting point, then learns
in real RocketSim worlds using PPO, human replay anchoring and a mixed opponent
pool. **It is no longer replay-only training.** Live RLBot exports remain frozen;
they do not train while playing. The original replay runs, source fingerprints,
parsed shards and exports are preserved.

The motivation is measured behavior, not a claim that extra epochs always help:
the supplied policy peaked near epoch 11 on validation while training loss kept
falling through epoch 15. Runtime fixes reduced long stalls but did not establish
good defending, useful touches or generalization. This branch gives the model
consequences for its own decisions instead of repeating the same demonstrations
indefinitely. No competitive improvement has been established by cloud tests.

## Install and start

Extract the source update into `E:\Downloads\Chat_GPT_AI`, replacing included
source files. Preserve `.venv` and all `data`. It uses existing Torch, RLGym,
RocketSim and W&B dependencies. It does not download models or reparse replays.

Run the small plumbing check first:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_HYBRID.bat check --device cuda
```

This performs 256 actual controlled decisions and optimizer updates in a separate
`replay_hybrid_check` run. Passing checks the plumbing; such a short run cannot
establish playing strength. It does not replace your current bot.

Start the actual run:

```bat
REPLAY_HYBRID.bat start --device cuda
```

Defaults:

| Setting | Default |
|---|---|
| Source | `rvq_runs\replay_rvq01\policy\best.pt` |
| New run | `rvq_runs\replay_hybrid01` |
| Training mode | 1v1 first |
| Worlds / decisions per rollout | 4 / 128 each |
| Budget | 1,000,000 controlled decisions, eight physics ticks per decision |
| Validation | Every 50,000 decisions; six paired 120-second matches |
| Final held-out evaluation | Twelve paired 300-second matches on new seeds |
| Replay anchor | Existing source run's prepared training split |
| W&B project | `slater-replay-hybrid`, using your local login |

The parallel batch can overshoot a target by a few decisions. Wall time depends
on the reported `samples_per_second`, plus checkpoint/evaluation costs. Quiet
power mode, a running game and CPU/GPU contention can change it considerably.
There is no promise that one million decisions makes a strong bot.

For a smaller allocation on the first launch:

```bat
REPLAY_HYBRID.bat start --device cuda --envs 2 --minibatch 64
```

Saved run settings are reused on subsequent launches when omitted. Changing
world count, team size, source, data, code, dependencies or opponent weights needs
a new run name; those changes affect the experiment. The total step target may
be extended without changing the experiment identity.

## What it learns

Starts mix ordinary kickoffs (20%), attacking positions (25%), defensive threats
(30%), recovery positions (10%) and aerial attacks (15%). Attacking balls start
stationary or with small neutral motion; they are not free shots rolling into
an empty net. Defensive balls threaten the controlled team's goal. Both colours
and varied positions are used.

The main reward is **+1 for scoring and -1 for conceding**. A small, bounded field
potential supplies `gamma * Phi(next) - Phi(previous)`, with zero potential on
terminal goals. It is not clipped or replaced with raw progress/touch rewards.
Its discounted sum telescopes, so repeatedly driving the ball back and forth
does not farm extra shaping return. Moving back to defend is not assigned an
additional arbitrary penalty. Time limits bootstrap the true final state;
advantages never cross resets.

There are **no rewards for pressing jump/boost, spinning, touching repeatedly or
performing arbitrary aerials**. Airborne touches and own goals are telemetry.
Recovery/aerial starts and the human replay anchor provide practice without a
button-press reward. This does not guarantee flashy mechanics will emerge.

Opponents mix the frozen original replay policy, a simple ball chaser and lagged
self-play snapshots. When `vendor\nexto\nexto-model.pt` exists, original Nexto is
also used. Nothing automatically downloads it. An existing model elsewhere can
be selected on the first launch:

```bat
REPLAY_HYBRID.bat start --device cuda --nexto "E:\path\to\nexto-model.pt"
```

Nexto uses its neural policy every eight ticks, without the RLBot kickoff script
or a separately modeled input delay. Results against this adapter do not equal
live RLBot results. Exact local weights and simulator versions are recorded.
The original traced Nexto model contains CPU-only tensor creation, so this
opponent runs on CPU even with `--device cuda`; the learning model stays on CUDA.
This update also accepts the previous hybrid release's exact code identity for
this fix only, recording `runtime_compatibility.json` while preserving existing
protocol hashes, checkpoints and progress. Rerun the same check/start command;
there is no need to delete a run or parse replays again.

## Preserve mechanics and keep value meanings correct

The action codec is frozen. Human replay cloning and a small KL anchor constrain
unlearning, with modest extra weight for demonstrated jump prefixes. They are
training losses, not forced runtime actions.

The original continuous offset depends on trainable state features. Changing it
would change physical controls for a fixed code while PPO accounts only for code
probabilities. Therefore this isolated child disables and freezes that offset:
the initial analogue difference is bounded by 0.05, and button thresholds are
unchanged. The parent remains exact and is included in paired comparisons.

PPO uses the **joint probability of all four autoregressive codes**, not the
probability of just one level. The fixed decoder makes that a well-defined
discrete control distribution. All car inputs reach the actual simulator.

There are two distinct value functions:

- A separate return critic learns the PPO return and is never used by search.
- The existing three search heads retain discounted-next-goal supervision from
  human replays and scored simulation episodes. Censored time-limit episodes do
  not become invented zero next-goal labels.

## Pause, resume and inspect

In a second CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_HYBRID.bat pause
```

Wait for `HYBRID_SAVED` before closing the training window. Resume with the same
start command. Actor, return critic, optimizers, lagged opponent, RNG state and
decision counters are checkpointed. Worlds reset on resume; it is not a bitwise
continuation of an unfinished physical trajectory. Force-closing may lose work
since the last checkpoint (normally at most five updates).

Evaluations also honor pause requests. Partial match results are discarded and
never used for selection. An interrupted final test is completed on the next
start command, even if the training step target was already reached.

```bat
REPLAY_HYBRID.bat status
```

Files under `data\isolated\replay_imitation\rvq_runs\replay_hybrid01`:

| File | Purpose |
|---|---|
| `protocol.json`, `dataset.json`, `model.json` | Actual source/data/settings and parameter counts |
| `source_snapshot\policy\best.pt` | Frozen parent snapshot; later parent updates do not replace it |
| `training\latest.pt` | Resume state, including optimizers and opponent snapshot |
| `policy\latest.pt` | Current inference weights, not automatically an improvement |
| `policy\best.pt`, `policy\selected.json` | Validation-selected weights; initialization retained if no gain |
| `training\events.jsonl`, `wandb_state.json` | Actual optimization and W&B records |
| `evaluations\validation_*.json` | Paired scores against fixed opponents/seeds, including each opponent separately |
| `heldout_matches.json` | Final selected model on independent seeds; not fed to training/selection |

The launcher log is `data\isolated\replay_imitation\hybrid_launcher.log`.
`--wandb-mode offline` and `disabled` are available. Never paste an API key into
the command or source.

## Selection, export and limits

Selection uses **actual simulated match goals**, not training reward or loss.
Candidate/source pairs use matching seeds, opponents and team colours. The
paired mean must improve; when Nexto is present, its subgroup cannot regress on
average. Six stale validation rounds stop the run. Final held-out matches use
independent seeds and report bootstrap uncertainty; small samples remain noisy.
Selection across repeated validation rounds is not an independent strength test.

If a validation improvement was selected:

```bat
REPLAY_HYBRID.bat export --name ReplayHybrid01
```

Load `data\rlbot_exports\ReplayHybrid01\bot.cfg` in RLBot v4. The default hybrid
export uses the **direct trained policy**, matching training and avoiding search
delay. The existing basic scripted kickoff remains available. For a separate
search comparison:

```bat
REPLAY_HYBRID.bat export --search --name ReplayHybrid01_Search
```

If no improvement was selected, the normal export refuses to call initialization
an improved model. For an explicitly experimental latest-weights comparison:

```bat
REPLAY_HYBRID.bat export --latest --name ReplayHybrid01_Trial
```

That export is labeled unverified. A held-out report is attached only when its
checkpoint hash matches the exported checkpoint. Existing exports are preserved;
choose a new name each time.

The initial training mode is 1v1. To start a separate 2v2 or 3v3 continuation from
a selected hybrid model, use a new run with `--source-run replay_hybrid01` and
`--team-size 2` or `3`. Strength in one format does not verify another format.

This is an implemented, tested training path, not an already trained strong bot.
Cloud tests exercise real simulator transitions, PPO likelihood/gradient math,
terminal/truncation handling, Nexto input parity, source preservation and resume.
No full dataset training or live-game strength has been established here.
Simulator mismatch, remaining policy limitations and weak value estimates can
still cause bad touches or own goals. Keep the parent for comparison and judge
the new run by its actual evaluations and live behavior.
