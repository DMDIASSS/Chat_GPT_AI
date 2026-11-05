# Candidate review v1.5.4

**Correction in v1.6:** a shared kickoff-template mutation made old orange resets non-repeatable. Historical kickoff comparisons were not reliably paired. See [the reset fix and Chronos branch](CHRONOS_TRAINING.md).


## What the latest reports establish

The three November 5 reports describe the same training state and published model. Collection reached 1,050,000 attempted teacher decisions. Revision 2 is active: the current buffer contains 246,874 accepted labels, every configured scenario, all four frozen teachers and 584 teacher takeovers from student attempts. About 63.5% of those active labels are kickoffs. All active opponents are scorer: the run is still in the beginner opponent stage, even though it now practices other scenarios too.

The best held-out candidate improved from the earlier best loss 4.279 to 3.739. Its action agreement is 17.27%, versus 11.31% for that earlier validation optimum. Relative to the still-published model, the candidate has lower held-out control error (0.355 vs 0.462) and higher button agreement (82.96% vs 77.34%). This is evidence of better teacher copying on the reused validation corpus, not evidence of better match play.

Watch/export/evaluation still resolve to the 250,000-decision model (SHA256 prefix 481c4dba5f74). The best held-out candidate is at 1,050,000 decisions (prefix 3fe0499ce04c). Both new evaluation files tested the old published checkpoint. Its kickoff result is 0 wins / 58 losses / 2 timeouts in 60 trials. Its mechanics screen against scorer has 3 goals with prior student contact, 28 losses and 39 timeouts; shots and defense still have zero touches. The earlier mechanics screen used a different opponent, so totals are not directly comparable.

The existing ten-start kickoff monitor retained the old published model. Earlier reports discarded rejected candidates' monitoring results, and a pause can occur before a round's final monitor. We cannot reconstruct which scores the latest candidate received from these reports. We must compare the actual candidate directly before diagnosing its playing strength or changing the selection rule.

## Run the new comparison before another long training session

1. Pause with **22** and wait for the training console to finish. Stop a viewer with Ctrl+C before merging files.
2. Extract the ZIP into the parent of chat_gpt_ai, merging chat_gpt_ai/novaforge. Keep .venv, assets and runs. Run **1_CHECK.bat**.
3. Run **33_COMPARE_COPY_CANDIDATE.bat**. It reads the current best-validation checkpoint from copy_state.json and verifies its recorded hash. It compares that immutable file against the published policy actually used by ordinary watch/export.
4. The comparison runs 60 kickoff trials per policy across scripted, scorer, Nexto, Ripple, Chronos and Galactus, plus 70 mechanics trials per policy against scorer. Both policies get the same seed/side starts, with new review seeds 950001 and 960001. This is simulator screening used for diagnosis, not a final independent strength benchmark. It can take several minutes.
5. Send the new copy02 report ZIP generated automatically in reports. The JSON comparisons are included in that report. No model is promoted by this command.
6. Optional: **34_WATCH_COPY_CANDIDATE.bat** opens the candidate against scorer. **24_WATCH_COPY.bat** still opens the published policy. The console prints the exact checkpoint and hash before watching.

Your copy02 student, optimizer and collected data remain in place. Launcher 32 is already applied according to these reports; it does not need to be run again for this update. Resume with 21 when ready.

## Manual commands

```bat
.venv\Scripts\python.exe run.py copy-compare --run copy02
.venv\Scripts\python.exe run.py watch --model runs\copy02 --copy-checkpoint validation --config runs\copy02\config.json --opponent scorer
```

watch/evaluate accept --copy-checkpoint published (the default), validation (best held-out candidate), or resume (latest optimizer checkpoint). Named candidate selection requires a copy run folder and checks its stored checkpoint hash. For a separate latest-optimizer comparison use:

```bat
.venv\Scripts\python.exe run.py copy-compare --run copy02 --candidate resume
```

## Report clarity

Reports now expose published, validation and resume checkpoint roles with hashes/timesteps; published metrics and candidate metrics have separate headings. The training phase is included. Future completed round monitors retain each measured candidate's kickoff results, including rejected candidates, instead of exporting only the winner. The old best_checkpoint field remains the published policy for compatibility.

The promotion criterion and learning algorithm are unchanged in this update. Candidate comparison holds the training lock and changes no training checkpoint pointers. It gives us the missing evidence to choose the next learning change. Kickoff overrides remain disabled.
