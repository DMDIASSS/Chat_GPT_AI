# Native replay planner optimization v2.1

Extract this source-only update into **E:\Downloads\Chat_GPT_AI**, replacing the
included runtime files. It uses the existing project, Python environment and
trained replay-imitation run. No extra packages or C++ compiler are required.

Run in CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --skip-reference --repeats 5
```

Results are written to a **new file**, preserving the earlier reports:

```text
data\isolated\replay_imitation\runs\replay_scratch01\native_runtime_v2_benchmark.json
```

Use `--run NAME` for a different existing run. Explicit `--device cuda` fails if
CUDA is unavailable; `--device auto` selects the available device. The report
records the actual device, checkpoint and vocabulary hashes.

## v2.1 comparison/reporting hotfix

The preceding comparator matched candidate lists by position. FP32 kernel
roundoff can change the ordering of close initial logits, so the same candidates
could be incorrectly rejected with `Native/reference candidate order differs`.
The comparator now matches branches by token and records whether their ordering
changed. The planner's candidate selection, inference and scoring are unchanged.

A changed candidate set, different final selected token, duplicate/missing
records, nonfinite values or errors above the existing tolerance still fail.
Actual mismatches are saved with per-token diagnostics and both sets of records.
The report is written before the launcher exits nonzero; failed paths are
excluded from recommendations. `validation_status` distinguishes `passed`,
`failed` and `not_checked`. Recommendations also state their forecast parity.

To recheck just the failing budget:

```bat
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --skip-reference --candidates 64 --repeats 5
```

Your latest GPU run measured 12 candidates at **51.63 ms median / 52.75 ms p95**,
with its forecast comparison passing. The 64-candidate frozen timing was
**214.57 ms median / 250.57 ms p95** and its comparison stopped at the order
check, so its forecast parity was not established. These are limited kickoff
timings; 12 candidates is the largest tested budget that met 66.7 ms in that run.

## Changes from v1

Your GTX 1650 measured **232.75 ms** for v1's 64-candidate search. The intended
8-tick action interval allows **66.7 ms**. This update targets additional overhead:

- Spatial cross-attention uses packed key/value projections and SDPA directly.
- The final temporal layer computes only the last query/output. Earlier layers
  still compute the complete causal history; all learned weights are reused.
- The default `frozen` network compiles and freezes that inference graph in
  memory using the installed PyTorch. There is no Triton installation, new
  checkpoint, quantization or reduced precision. Construction/compilation time
  is reported separately as `network_setup_ms`.
- Native control objects and exact control-change boundaries are cached for
  each action token, avoiding repeated allocations and NumPy comparisons.

The full **64 candidates, one-second horizon, FP32 precision, value heads and
first eight executed ticks** remain available. All jump, flip, steering, boost
and powerslide edges are preserved, including partial terminal chunks. Compact
stepping reuses one arena with the preceding state reconstruction semantics.
The optional worker and global-pool stepping modes remain available.

This uses RocketSim, the simulation engine also used by GigaLearn. Python still
schedules simulation and builds observations. It is not an all-C++ GigaLearn port,
and high aggregate training SPS does not establish single-decision latency.

## Comparison and controls

The default CLI compares **4, 8, 12, 16 and 64 candidates**. The intermediate
budgets help locate the largest measured search fitting 66.7 ms. They are
explicitly labeled; fewer candidates are not assumed equally strong.

For every budget, the default also times the preceding native network and checks
candidate sets, scores, values, uncertainty and the selected token, matching
records by token. A mismatch above `1e-4` or a changed selection is recorded as
a failure; the launcher exits nonzero after saving all results. `--skip-reference` skips
only the older Python reference timing; the native comparison still runs.
Without that flag, the Python reference is measured and compared as well.
`--skip-native-comparison` disables the extra native comparison explicitly.

Other settings:

```bat
REM The algebraic optimization without graph freezing:
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --network optimized --skip-reference

REM The preceding neural path:
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --network original

REM Parallel native stepping is an experiment, not a promised improvement:
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --stepping workers --workers 2 --skip-reference

REM Team-mode latency:
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --team-size 2 --skip-reference
```

`--threads 2` controls Torch CPU threads. `--team-size 3` measures 3v3.
`--stepping multi_step` uses the wheel's global thread pool, which may incur
excess worker overhead. No simulation settings are changed automatically.

Reports include individual samples, warmed medians, estimated p95, first-call
latency and phase medians. The 64-candidate phase breakdown is also printed in
CMD. `recommended_backend_by_candidates` selects the faster measured backend by
p95 for each budget; it can retain the preceding path if the new one regresses.
This recommendation does not change a gameplay adapter's configuration.

## Verification and limits

Tests check neural outputs with several batch and history lengths, source-weight
preservation, both teams in 1v1/2v2/3v3, ordinary and goal-ending forecasts,
repeated searches and partial control chunks. Dense-contact step comparisons
start from matching cloned collision graphs: separate arenas can order initially
overlapping contacts differently even with ordinary stepping.

```bat
.venv\Scripts\python.exe -m pytest -q tests\test_replay_inference.py tests\test_replay_runtime.py tests\test_replay_native_runtime.py
```

On the cloud CPU, with matching 3.27M **random fixture weights** and the supplied
vocabulary, five-call 64-candidate medians were about **523 ms original native
versus 219 ms v2 frozen**. The v2 p95 was about **361 ms**, so it still failed
66.7 ms there. CPU timings have varied across runs. These numbers are not a
GTX 1650 result or evidence of playing strength.

There is no CUDA device in the cloud, and the uploaded checkpoint exceeds the
file tool's 32 MiB transfer limit. Run the command above to measure your actual
weights and GPU. Seeded kickoff timing does not establish full-match worst-case
latency. Repeat invocations replace only the new v2 benchmark report.

All runtime changes are outside `replay_il/`, preserving its pinned training
source hashes and resume compatibility. Existing checkpoint and vocabulary hash
checks remain active. No optimizer state, datasets or training results are changed.
This is an inference/backend update, not a playable adapter for the chunk model.
Your uploaded kickoff book is empty; no pro kickoff is supplied or claimed.

The linked PPO guide was reviewed separately: see [REPLAY_REWARD_DESIGN.md](REPLAY_REWARD_DESIGN.md).
This run remains supervised imitation and value regression; this patch adds no
RL stage and does not silently change rewards or learned value targets.
