# Selector diagnostics and Triad watch fix

## Run the diagnostics

1. Run **8_PAUSE_SELECTOR.bat** in `Chat_GPT_AI/triadbot`, then wait for the
   training console to finish saving. Keep Fusion paused too.
2. Copy this ZIP's `chat_gpt_ai/novaforge` and `chat_gpt_ai/triadbot` folders into
   your existing `Chat_GPT_AI`. Replace program files; keep `.venv`, `assets`,
   `runs` and `exports`. No new dependency installation is needed.
3. Run **13_DIAGNOSE_SELECTOR.bat** in `triadbot`.
4. Let all games finish. It prints each game, score and running progress during
   longer games. Ctrl+C cancels and keeps earlier complete reports.
5. Send the ZIP printed after **DIAGNOSTIC_REPORT_READY**. It is under
   `Chat_GPT_AI/triadbot/reports/selector01_diagnostics_<UTC timestamp>.zip`.
   You can also run 12_RESEARCH_REPORT.bat afterward; it includes the latest
   completed diagnostic. Do not resume training before reviewing the findings.

Default for a Breakout selector: **48 games, 30 simulated seconds each**. They
cover four opponents, both team colors and six controller/body conditions:

| Controller | Learner body | Purpose |
| --- | --- | --- |
| Latest learned selector | Training body (usually Breakout) | Measure its choices/probabilities |
| Fixed Chronos | Same training body | Chronos-only control |
| Fixed GalactusV2 | Same training body | Galactus through the same adapter |
| Fixed Ripple v1.1 | Same training body | Ripple through the same adapter |
| Fixed GalactusV2 | Octane reference body | Check sensitivity to the learner hitbox |
| Fixed Ripple v1.1 | Octane reference body | Check sensitivity to the learner hitbox |

For an Octane-trained selector the extra condition is Chronos/Breakout, so there
are 40 games instead. Opponent hitboxes remain assigned by the existing native
opponent adapters. The comparison intentionally changes the learner's body;
initial observation equality is required only within the same body/seed/color.

## What the report means

`free_choice_probabilities.latest` reports the mean, spread, range, entropy,
top-two probability margin, greedy choices and difference from initial weights
**only when all three experts can be selected**. Forced commitment decisions
are counted separately and excluded from the probability audit. Otherwise a
one-hot action mask would misleadingly look like 100% confidence.

For example, 40% / 35% / 25% with Chronos always largest is different from
99% / .5% / .5%, although deterministic play chooses Chronos in both cases.
The initial network is queried on the same observations and commitment context
visited by the latest selector; it is not an independent initial-policy rollout.
Statistics are also grouped by opponent. They describe the visited kickoff-match
trajectories, not every possible aerial/recovery/wall state or training sample.

`summaries` contains actual timed W/D/L and goals for every fixed expert/body.
`paired_vs_fixed_chronos_same_body` compares controllers using matching starts.
`reference_body_effects` reports the separate hitbox changes. A poor fixed-expert
result can explain why choosing it is unattractive under this adapter. Small
differences need repeated/longer tests; these exploratory checks cannot promote
a champion or prove that a particular expert is universally strongest.

Every condition uses the same common eight-tick decision execution with the
planned seven-tick plus simulator one-tick delay. Ripple's held-control queue
approximation remains. These tests investigate common-adapter and hitbox effects;
they do **not** establish exact parity with each expert's original native timing.
Native automatic demo respawn randomness and platform floating-point differences
also remain. Matching initial hashes does not guarantee identical full matches.

The JSON records model/source/teacher identities, installed versions, body,
seeds, duration, wall time and complete trial results. The command verifies that
checkpoints, model metadata, config, guard, status, experiment identity and the
training STOP flag remain unchanged. It writes only diagnostic artifacts and its
own stop marker/lock. No weights, raw observations or credentials are included in
the shareable ZIP. It neither trains nor promotes nor clears a regression halt.

Optional commands from a CMD opened in `triadbot`:

```bat
rem Longer exploratory comparison (96 games for a Breakout selector):
..\novaforge\.venv\Scripts\python.exe -u run.py selector-diagnose --pairs 2 --seconds 60
rem Skip body variants (32 games at one pair):
..\novaforge\.venv\Scripts\python.exe -u run.py selector-diagnose --pairs 1 --seconds 30 --skip-body-check
```

## Watch 1 / 5

`1_WATCH_TRIAD.bat` watches random routing; `5_WATCH_SELECTOR.bat` watches the
latest learned selector. Both now print immediately and run Python unbuffered.

The launch bug was a working-directory mismatch: setup put the checked viewer
and camera settings in `novaforge`, while the second project started Python in
`triadbot`. The native sender launches `./rlviser.exe`. The watch wrapper now
resolves a selector path first, runs from `novaforge`, then restores the original
directory on exit/error. This lets the sender find the prepared executable and
the 110 FOV / 270 distance / 100 height / -4 pitch ballcam settings.

Stop earlier watch consoles with Ctrl+C and close their RLViser windows, then
run 1 or 5. A busy watch lock now gives this recovery instruction. If another
error remains, paste the complete console text; this fix does not diagnose every
possible GPU/window/network problem. The native Windows graphical viewer still
needs testing on the user's PC.
