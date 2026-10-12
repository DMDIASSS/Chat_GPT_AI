# Native quality campaign

For the continuous overnight loop, use
[SLATER_NATIVE_OVERNIGHT_README.md](SLATER_NATIVE_OVERNIGHT_README.md) and
`NATIVE_10_OVERNIGHT_ALL.bat`. The campaign described below is finite.

This update runs a finite replay-pretraining and improvement campaign, then
compares retained candidates with Nexto and your protected update180. It does
not replace the original checkpoints or promise SSL strength.

## Start on your PC

1. Stop training and AutoLeague before replacing code or rebuilding.
2. Extract `Slater_Native_Quality_Update.zip` directly into
   `E:\Downloads\Chat_GPT_AI`, replacing the included code files.
3. Run `NATIVE_2_BUILD.bat` and check that the build succeeds. This rebuild is
   required: the new evaluation probe and opponent controls change the binary.
   The installer upgrades the known previous source patch without deleting it;
   unknown local source edits still stop the installer.
4. Run `NATIVE_8_RUN_ALL.bat`. Leave this window open. It prepares your local
   `data\replays\ranked-duels` folder and then runs the whole campaign.
5. Run `NATIVE_9_STATUS.bat` in another window to see saved progress.

Equivalent CMD commands, after rebuilding:

```bat
cd /d E:\Downloads\Chat_GPT_AI
NATIVE_8_RUN_ALL.bat
```

Replay parsing and match evaluation can take hours. This is substantially more
work than the five-second native smoke test. Matches print progress and ETA.
After an interruption, rerun the same launcher: completed matches and saved
training checkpoints are reused. An unfinished game is replayed. Keep the
input files, code and settings unchanged when resuming; changed protocols
require a new campaign name. This campaign stops after two rounds.

`NATIVE_8_SELECT_ONLY.bat` compares the existing models without new training,
using your existing `ranked_duels_bank01.bin` and a separate
`native_quality_screen01` campaign. Its screen results do not replace the full
campaign's independent final comparison.

## What it runs

- Automatically finds the latest original C++ model, replay checkpoint series
  (first/middle/latest), update180 and Nexto. It screens this small shortlist
  instead of comparing hundreds of checkpoints.
- Parses up to 500 available local replay files, makes a larger training bank,
  and keeps replay groups separate across training, validation and test splits.
  No Discord token or replay download account is needed.
- Copies the screened native baseline into a new run for five replay behavior
  cloning epochs and two PPO iterations. Independent match results decide
  whether this becomes the native baseline.
- Measures nine practice tasks and runs a mixed and a focused branch from the
  same baseline. Each branch receives two million additional learner
  decisions per round, with at most one PPO iteration of budget overshoot.
- Uses frozen native past policies during C++ training. Frozen opponents have
  scripted kickoff controls applied every physics tick. Learner actions stay
  on-policy. Nexto and update180 are evaluation opponents; their attention
  weights cannot directly load into this native MLP trainer.
- Rewards useful air carries and goal-linked finishes, actual wheel-contact
  flip-reset acquisition and use, and selected defense/recovery practice.
  There is no standalone bump-farming bonus. Retention checks include other
  mechanics and 2v2/3v3 before accepting a changed native baseline.
- Uses separate screening, qualification and confirmation match seeds, both
  colors, fixed opponents, paired confidence intervals and conservative
  promotion rules. Final confirmation uses 16 fresh seeds per color/opponent
  and five-minute simulated games. All evaluation policies have scripted
  kickoffs enabled. Close results keep the playing incumbent.
- Reports the untouched replay test split only after final selection. That
  report is not used to choose the checkpoint.

## Results

The full campaign writes to:

```text
data\isolated\native_quality\campaigns\native_quality01\
```

Read `selected.json` for `playing_checkpoint`, `native_checkpoint` and the
selection status. `CLOSE_OR_INCONCLUSIVE` means improvement was not established
by the confirmation games. `PROVISIONAL_SCREEN_LEADER` means the native lineage
has not passed the improvement gates. These statuses are useful outcomes,
not a reason to replace update180 manually.

`progress.json` includes the current round and history. `initial`,
`bootstrap_selection`, `round_01`, `round_02` and `final` contain match evidence;
each selection has `screen.json`, `qualification.json`, `confirmation.json`
and frozen finalists. Each round also records `weaknesses.json`.
`untouched_replay_test.json` contains the final replay diagnostic.

New native training runs and logs stay under
`data\isolated\gigalearn_native\runs\native_quality01_*`.
Replays and existing weights are preserved. Old native runs pin their binary
identity, so they cannot resume with this changed executable; the campaign
instead copies their complete checkpoint into a new run.

The native evaluation adapter checks its observations, masks and predictions
against the C++ executable before matches. It preserves the pinned backend's
boost-timer layout. Evaluation uses Python RocketSim 2.2.1, while training uses
the pinned C++ RocketSim 2.1.1: inference parity does not prove physics parity
or live Rocket League strength. Native `.lt` checkpoints still need a separate
RLBot/browser deployment adapter and live verification. Your existing Nexto
and update180 export path remains the playing-model path.

Cloud validation is recorded in [docs/NATIVE_QUALITY_VALIDATION.md](docs/NATIVE_QUALITY_VALIDATION.md).
Actual selection requires your local replay files and trained checkpoints.
