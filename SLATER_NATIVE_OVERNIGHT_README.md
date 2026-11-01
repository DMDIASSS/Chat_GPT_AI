# Overnight replay + mechanics + checkpoint league

Install `Slater_Native_Replay_Kickoff_Update.zip` into `E:\Downloads\Chat_GPT_AI`,
replacing the included code. Stop any other training or AutoLeague first.
Run
`NATIVE_2_BUILD.bat` before starting. This update adds native kickoff imitation; rebuilding is required even if the
previous Native Quality build succeeded. Older runs and checkpoints are kept.

Run **`NATIVE_10_OVERNIGHT_ALL.bat`** and leave its window open. It starts or
resumes `native_overnight03` with the same command. Plug in your laptop and
disable automatic sleep. `NATIVE_10_STATUS.bat` shows its saved stage and cycle.

## What stays running

1. Prepare the available local `data\replays\ranked-duels` replays, up to 500
   files, and reuse the prepared dataset/bank on later launches. Training,
   validation and test sources are kept separate. Replay controls are inferred
   labels, not exact human inputs. Parsing uses the existing Python replay
   reader or prepared captures; policy learning runs in C++ GigaLearn.
2. Screen the existing original/replay native checkpoints, Nexto and update180.
   Check every native policy's observation/mask/inference against the C++ probe.
3. Make a protected native copy for five behavior-cloning epochs and two PPO
   iterations. Screen every checkpoint from this replay-pretraining run.
4. Repeatedly measure mechanics, train a mixed and a focused native branch,
   and screen every checkpoint saved by each branch. Each branch trains one
   million additional learner decisions before returning for comparison.
   Iteration boundaries may add a little more than the requested budget.
5. Keep close exploration lineages progressing, while preserving the archive
   leader. A branch that falls more than 0.5 goals/game below the screen leader
   restarts from that leader in a new run; its old checkpoints are retained.
6. Every third cycle, freeze the challenger and run fresh confirmation games
   against the retained playing incumbent. Acceptance also requires mechanics
   and 2v2/3v3 retention checks. Confirmation attempts share a summable error
   budget, preventing an indefinite loop from treating repeated lucky tests
   as independent proof of improvement.

Screens use **two seeds, both colors and 45 simulated seconds/game**, with
the same frozen rivals and seeds for every model. That is eight games/model
when both Nexto and update180 exist. Confirmation uses twelve fresh seed
pairs, both colors and 90 seconds/game. Screens guide exploration and give a
comparable shortlist; they are not five-minute full-match certification.

Training always uses frozen **native** past-policy opponents with scripted kickoff
by default (`old_chance=1`). The new run also screens up to two leaders from
your previous `native_overnight02` shortlist when present.
Every evaluation policy also has scripted kickoff enabled. Nexto/update180
are evaluation rivals, not directly loadable C++ training opponents.

Mixed/focused training includes replay resets, standard starts, ground,
defense, recovery, low boost, aerial, wall, air-carry and reset-use practice.
Rewards include useful air carries, goal-linked finishes and actual flip-reset
acquisition/use. The loop also records practice specialists across nine tasks.
These practice scores do not certify mastery.

## Your morning results

Open:

```text
data\isolated\native_quality\campaigns\native_overnight03\SHORTLIST.md
```

It lists the top ten native models with checkpoint paths, average goal
difference and wins/draws/losses, plus practice specialists and the confirmed
playing incumbent. `shortlist.json` is the machine-readable equivalent.
`models.json` includes **every completed checkpoint screen**, not just the
top ten. `screens` contains individual match records; `confirmations` contains
fresh evidence and conservative verdicts. `status.json` records the stage.

Checkpoints and logs are in:

```text
data\isolated\gigalearn_native\runs\native_overnight03_*
```

The shortlist updates after each completed model screen, so you can read it
even before a cycle or confirmation finishes. Close results keep the playing
incumbent. No checkpoints are deleted and no original champion is overwritten.
Later models can regress: the last saved model is not automatically best.

## Pause and resume

Run **`NATIVE_10_PAUSE.bat`** in another window. Native training finishes and
saves its current PPO iteration. Evaluation saves its current match and stops
before the next one. Replay parsing finishes its current preparation command;
behavior cloning reaches the subsequent PPO boundary before pausing.

Wait for `OVERNIGHT_PAUSED` (or saved `PAUSED` status) before closing the
training window. Resume by running **`NATIVE_10_OVERNIGHT_ALL.bat`** again.
Completed training chunks and match records are reused. A partly completed
chunk continues from its last complete native checkpoint.

The loop has no normal cycle limit. It pauses when asked or when free disk
space falls below **10 GiB**; errors stop it with diagnostic status. It retains
all models, so disk use grows. Input files, code, settings and binary identity
are pinned: changing them requires a new run name. Do not run the finite
campaign or a separate trainer simultaneously on the same laptop.

For a bounded experiment, the Python command supports `--max-cycles N`.
For separate runs/settings, use `--run NAME --config settings.json` on all
run/pause/status commands. A config overrides the defaults in
`slater_native_overnight.py`; prepare and checkpoint identities remain checked.

The untouched replay test is deliberately not repeatedly opened by the
adaptive overnight loop. Run that diagnostic once after freezing a final
candidate. Native `.lt` deployment into RLBot/browser still needs its own
adapter and live verification; cloud integration does not establish SSL rank
or simulator physics parity.

## Optional API replay supply

Run `NATIVE_11_REPLAY_API_SETUP.bat` once. Paste your Ballchasing API token
into the hidden local prompt. It stays under ignored
`data/isolated/native_replay_supply/ballchasing_token.txt`; never put it in Git
or chat. Alternatively provide `BALLCHASING_TOKEN` or `BALLCHASING_API_KEY`
as a local environment variable. No key is required to use existing replays.

The public configuration is `data/isolated/native_replay_supply/config.json`.
Defaults follow your requested window: ranked duels, 2021-01-01 through
2026-10-12, both reported player ranks in tiers 21–22 (GC3/SSL). The API search
uses its documented broader Grand Champion filter; returned player metadata
is checked for the exact tiers. Unknown ranks are skipped, not labelled SSL.

Every fourth completed cycle, the loop checks for unseen local replays first.
When those are exhausted, it acquires a bounded fresh batch of up to 64 files.
The local download budget is 180 attempts/hour; HTTP 429 and Retry-After cause
a cooldown. Training reuses its current bank rather than waiting for the limit
or trying to bypass it. Old replay banks are immutable and old runs keep their
original bank identity. A new batch is parsed into a separate bank, receives
two BC epochs in a protected new run, and its models are screened before the
next training chunks. Failed parsing retains the previous training bank.

The GitHub `rl-high-level-dataset` collection pipeline itself uses Ballchasing.
The fallback implemented here uses the published Kaggle dataset independently:
individual bounded duel `.replay` files, never a whole large archive. If the
service requires credentials, it supports local `KAGGLE_USERNAME` and
`KAGGLE_KEY`. If only large bundles are exposed or network access is unavailable,
it keeps training from cached replays. For an already downloaded dataset, set
`kaggle_local` to its root folder containing `1v1`/`duel` mode directories.
The upstream curated fallback has a different quality claim from exact
Ballchasing GC3/SSL metadata filtering; provenance is recorded with each file.

Replays are reusable training data. Fresh batches increase variety; files do
not disappear or become unusable after a training pass. Downloads and batch
provenance stay under ignored data folders. Live Ballchasing/Kaggle downloads
were not verified in this cloud because their endpoints are inaccessible here;
quota handling, strict metadata filters, fallback and cache retention have
fixture tests.

## Learning kickoffs instead of depending on the script

Each new native chunk receives a small C++ scripted-demo imitation phase.
Physical cars execute the existing seven-stage kickoff script; its controls
are projected to the nearest legal action in the learner's 90-action table.
The learner imitates those controls with validation and rollback. This is an
approximation: continuous teacher inputs and four-tick stages cannot be
reproduced exactly by an eight-tick discrete policy.

Only the policy head changes during kickoff imitation. Shared mechanics
features and the critic stay frozen; a train-only replay-state KL anchor limits
policy drift. The script-driven samples never enter PPO. During subsequent PPO
the learner chooses its own actions against scripted frozen opponents, so its
actions and log probabilities describe the actions actually executed. Simply
overriding its controls while crediting sampled actions would break that link.

Each cycle writes `unscripted_learner.json`: learner script OFF, rival scripts
ON, both colors. The shortlist links this report separately from the normal
scripted comparisons. Good demonstration loss or scripted match results do
not establish stronger raw kickoffs; judge the unscripted reports too.

Because the executable and protocols changed, the launchers use the new name
`native_overnight03`. Pause `native_overnight02` with its old launcher before
extracting this update, then rebuild and start the new launcher. Original
models and the old shortlist are preserved.
