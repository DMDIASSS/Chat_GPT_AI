Current evaluator: [PAIRED_REPAIR.md](PAIRED_REPAIR.md). The binary hash and timings below describe the earlier autonomous release; the current executable/hash is in native_release.json.

# Autonomous controller validation

The executable is unchanged: fixed-rollout-v1, SHA256
`3fc3eaaa51af944d2a87773f9aebcbc82b12812778d53af9ed64a106fc46e128`.
It was verified in Windows native workflow 42306980807. This controller is checked
by `.github/workflows/gigaforge-autonomous.yml`; consult the Actions result for
the source commit in the release record.

Linux CPU checks cover fixed-budget statistical decisions; attack, defense and
individual-opponent regression rejection; a summable confirmation error budget;
cache invalidation on actor changes; partial evaluation pause/resume; corrupted
cache rejection; bounded shortlist copies surviving source deletion; late
population mutation; and predecessor-lock rejection before new-run creation.
Windows-specific access checks are skipped on Linux and run in Windows CI.

Actual native integration exercises eight reward/family combinations, data
accounting, actor updates, shared-trunk freezing, checkpoint optimizer resume,
legacy study compatibility, v2 training and batch evaluation, cache reuse and
preserved actors. Synthetic verdicts separately exercise controller confirmation,
rejection and protected promotion. Those synthetic verdicts do not measure skill.

An isolated managed Linux CPU timing check used the same 256-game workload with
10 simulated seconds per game: four jobs of eight seed pairs took 30.37 wall
seconds; one job of 32 pairs took 25.60 seconds (about 19% more decisions per wall
second). This includes process/model-loading overhead. It is one small timing
check, not a universal speed claim or a GTX 1650 Ti benchmark. CPU and GPU batch
scaling differ; the 60-second tournament remains the actual strength evaluation.

Short native integration matches are intentionally too short to establish
strength. No new trained champion or claim of improved Rocket League play is
included in this update. The five-hour user study supplies that evidence.
