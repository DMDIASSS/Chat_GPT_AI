# Four-expert selector with a selected and refined local Fusion teacher

This is a separate 1v1 experiment. Existing `selector01`, `fusion01` and Chronos
runs are preserved. Source ZIPs contain no weights. The new selector does not
become stronger merely because it has four choices.

## Install

Pause old selector/Fusion training, wait for saving, and stop watch consoles with
Ctrl+C. Copy the ZIP's `chat_gpt_ai/novaforge` and `chat_gpt_ai/triadbot` folders
into your existing `Chat_GPT_AI`, replacing program files. Keep `.venv`, assets,
runs and exports. No reinstall is needed. All numbers below are in **triadbot**.

## Workflow

| Launcher | Action |
| --- | --- |
| 14_COMPARE_SAVED_FUSIONS | Test available distinct trained Fusion checkpoints and confirm finalists on fresh seeds |
| 15_PREPARE_FUSION_REFINEMENT | Create `novaforge/runs/fusion_refine01` from the best tested trained Fusion |
| 16_REFINE_FUSION_128K | Train/resume toward 131,072 new refinement decisions, then stop |
| 17_CREATE_FOUR_SELECTOR | Freeze the refinement's retained champion into new `triadbot/runs/selector04` |
| 18_TRAIN_FOUR_SELECTOR | Train/resume the four-way selector until paused or regression-halted |
| 19_PAUSE_FOUR_SELECTOR | Request a safe stop for selector04 |
| 20_WATCH_FOUR_SELECTOR | Watch the latest four-way gate and corrected probability logs |
| 21_DIAGNOSE_FOUR_SELECTOR | Read-only fixed-expert/probability/body comparison; pause with 19 first |
| 22_EXPORT_FOUR_CHAMPION_V5 | Export the retained four-way champion, including the frozen Fusion actor |
| 23_REPORT_FOUR_SELECTOR | Shareable four-way report; pause first |
| 24_PAUSE_FUSION_REFINEMENT | Safely stop the separate bounded Fusion refinement |

Run 14 first. It requires the original Fusion runs to be paused (NovaForge's
44 pauses fusion01). It searches `novaforge/runs/fusion*` folders with a Fusion
state/config, including retained `.zip` checkpoints, `.lt` snapshots and protected
champions. Exact parameter duplicates are removed; original-Chronos duplicates
are not added as a fourth expert. Corrupt/incompatible files and omitted models
are listed in the report. Deleted/pruned checkpoints cannot be recovered.

The default limit is 12 distinct candidates. If more exist, the report lists
those not tested. To test all available candidates explicitly, use
`--max-candidates 0`. This can take much longer. These are immutable actors, not
weight averaging. The selected model is the **best tested trained candidate**,
not a guarantee of a globally best Fusion checkpoint.

Screening uses four frozen opponents, both colors, one seed pair and 30-second
games. The top two trained candidates and original Chronos are then tested on
a different seed bank using two pairs and 60-second games. Confirmation match
points determine the selected trained candidate; goal difference breaks ties.
Original Chronos is a separate control, and the report states the difference
against it. A trained winner can still be worse than original Chronos. This
tournament never promotes or replaces an existing deployment champion.

Launcher 14 saves all tested actors and results under
`triadbot/fusion_selection/<UTC timestamp>/` and prints a report ZIP under
`triadbot/reports`. Each actor is roughly 15 MB; multiple selections can consume
substantial disk space. The selection records source/parameter hashes, seeds,
body, match duration, scores, runtime and skipped candidates. Training locks and
before/after hashes protect source runs. Ctrl+C preserves earlier complete
selections. The fixed body is Breakout, matching the proposed selector; this is
not a comparison of each candidate on every possible car body.

After 14, run **15**, then **16**. The new refinement starts from the selected
Fusion's actual actor weights. It creates a fresh critic and optimizer, freezes
its anchor to that Fusion actor, and keeps the selected initialization as its
initial champion. Thus refinement step zero means the selected **trained Fusion**,
not original Chronos. It retains the existing goal/potential objective, critic
warmup, conservative actor updates, snapshot self-play and regression guard.

The 131,072-decision budget includes approximately 32,768 critic-warmup decisions
under the standard two-worker rollout. Remaining time varies by hardware. Restarting
16 resumes toward the same total budget instead of adding another full budget.
PPO rounds to a complete rollout. A guard can stop it earlier. Source Fusion runs
are not resumed or modified by this workflow.

The refinement opponent mix keeps the existing frozen league and snapshot
self-play, scaled to 95%, plus **5% original scripted demochaser** stress. That
script chases the opposing car rather than the ball. It is not the third-party
Adversity bot, and is not claimed to be an elite demo specialist.

Once refinement finishes, run **17**. It checks that refinement belongs to the
same selected model and freezes its retained champion. If refinement did not
earn promotion, the frozen teacher remains the selected trained Fusion. A new
selection requires a new refinement name; existing runs cannot be overwritten.
An explicit `--direct` option can create a four-way run from the selected student
without refinement, but the numbered default follows the refinement workflow.

Then run **18**. This trains a fresh small selector with **236 inputs and four
outputs**: Chronos, GalactusV2, Ripple v1.1 and local Fusion. It is not the old
three-output network with an extra label. The experts remain frozen. Initially
the greedy choice is Chronos; training samples all four. The commitment remains
eight decisions, approximately .53 seconds. The three-way model/contract stays
supported and untouched.

Four-way training opponents are Chronos/Galactus/Nexto/Ripple at 23.75% each,
plus 5% scripted demochaser. The current selector still does not have selector
snapshot self-play; **the Fusion refinement does**. Broader opponent names in
the candidate audit are not silently enabled before verified adapters exist.

Pause with **19** before diagnostics/reporting. Launcher **21** has 56 short games
for a Breakout four-way selector, including fixed Fusion through the same common
adapter. It measures only free-choice probabilities and preserves models/guards.
Launcher **22** exports the retained champion. Until promotion, that gate routes
to Chronos, although all four frozen experts are bundled. The export includes a
hash-locked Fusion actor and matching metadata under `assets/fusion`. Existing
standalone exports need re-exporting to receive the updated runtime source.

You can use the existing manual evaluation command for this run:

```bat
..\novaforge\.venv\Scripts\python.exe -u run.py selector-evaluate --run selector04 --split validation --pairs 4 --seconds 60
```

## What this does and does not establish

New free-choice logs use the actual learned actor, not the unused fair scheduler.
See [telemetry explanation](SELECTOR_TELEMETRY_v1.10.md). The earlier diagnostic
is still valid; no rerun is needed merely to fix the watch display.

All conditions use the common eight-tick/7+1-delay adapter. Ripple's held-queue
approximation is not native Ripple timing/history. Poor common-adapter results
cannot establish that native Ripple is weak. Model licenses and notices remain
with their authors; local downloads/exports do not grant new redistribution rights.

Local/CI short smokes verify selection, refinement, frozen weights, resume,
metadata and v5 protocol execution. They do not establish strength. Real 1v1
comparisons, multiple seeds and regression protection are still needed on the
user's hardware. [Candidate audit and team-play plan](EXPERT_AND_TEAM_PLAN_v1.10.md).
