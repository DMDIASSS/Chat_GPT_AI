# Compare the six existing runs against Nexto

Extract this update into `E:\Downloads\Chat_GPT_AI` and double-click
**COMPARE_C0001_C0006_NEXTO.bat**. It evaluates/resumes; it never starts training.
Use **COMPARE_C0001_C0006_PAUSE.bat** to pause at a completed-game boundary.
Rerun the start file to resume. Your existing project, Python, Nexto weights and
native simulator build/dependencies are required; this ZIP is a source update.

The preset includes every actor, including checkpoint zero:

| Runs | Checkpoints per run | Paths |
|---|---|---|
| c0001–c0002 | 000000–000080 inclusive | 162 |
| c0003–c0006 | 000000–000100 inclusive | 404 |
| Total | | **566** |

Missing files stop the launcher and are listed in
`data/isolated/checkpoint_comparison_audit.json`; they are not silently skipped.
Identical actor weights are evaluated once, with all original paths retained.
Both teams use the same scripted-kickoff setting. Each candidate fills its whole
team: candidate+candidate versus Nexto+Nexto in 2v2, and three of each in 3v3.

The complete screen uses all candidates, three formats, two independent seeds,
both team colors and 30 seconds per game: up to **6,792 games** before weight
deduplication. Seeds are shared across candidates for paired comparisons.
These are short exploratory games, not a reliable final strength certification.
No early-loss streak truncates a candidate's test. Existing models are preserved.

**COMPARE_C0001_C0006_RESULTS.bat** writes an Excel-readable
`EVERY_CHECKPOINT_VS_NEXTO.csv` inside the selection run, including every alias,
format, goals, wins/draws/losses and completion count. Rerunning start also writes
it automatically. The normal selection `stages/screen/ranking.json` and
`SHORTLIST.md` remain available. Incomplete rows are explicitly marked.

To use Training Studio instead, load **STUDIO_C0001_C0006_NEXTO_ALL.json** and
run the model comparison through **screen**. Its 100,000-game invocation budget
allows the entire finite screen to finish. The standalone launcher checks all
expected files before launching; Studio's existing importer reports unavailable
sources through its inventory. Do not start native training to run this preset.
