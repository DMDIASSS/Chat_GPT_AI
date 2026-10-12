# Overnight replay + mechanics + checkpoint league

Install `Slater_Native_Overnight_Update.zip` into `E:\Downloads\Chat_GPT_AI`,
replacing the included code. Stop any other training or AutoLeague first.
If you have not successfully rebuilt after the Native Quality update, run
`NATIVE_2_BUILD.bat` before starting. This overnight update adds Python
orchestration; it requires that updated GigaLearn executable.

Run **`NATIVE_10_OVERNIGHT_ALL.bat`** and leave its window open. It starts or
resumes `native_overnight02` with the same command. Plug in your laptop and
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

Training uses frozen **native** past-policy opponents with scripted kickoff.
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
data\isolated\native_quality\campaigns\native_overnight02\SHORTLIST.md
```

It lists the top ten native models with checkpoint paths, average goal
difference and wins/draws/losses, plus practice specialists and the confirmed
playing incumbent. `shortlist.json` is the machine-readable equivalent.
`models.json` includes **every completed checkpoint screen**, not just the
top ten. `screens` contains individual match records; `confirmations` contains
fresh evidence and conservative verdicts. `status.json` records the stage.

Checkpoints and logs are in:

```text
data\isolated\gigalearn_native\runs\native_overnight02_*
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
