# Replay planner: multicore CPU forecasts

Further speedup is possible; the preceding 178 ms result is an implementation
measurement, not a demonstrated hardware limit. This update targets the roughly
119 ms spent in CPU simulation/state extraction. It does not guarantee that all
64 candidates will fit the 66.7 ms deadline.

Extract this small source update into **E:\Downloads\Chat_GPT_AI**, replacing all
included files. It needs the existing project, trained model and Python
installation. No new package or C++ compiler installation is required.

Run in CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_MULTICORE_BENCHMARK.bat --device cuda
```

This compares the preceding **compact/frozen** backend with **four CPU worker
processes/frozen**, at 12, 16, 32 and 64 candidates. Both use the same network, FP32
precision, full one-second horizon, first eight executed ticks and scoring.
Candidate sets, per-token scores/values and selected actions are checked. It
writes a separate report:

```text
data\isolated\replay_imitation\runs\replay_scratch01\native_runtime_multicore_benchmark.json
```

The original compact mode remains the default in `REPLAY_IL_NATIVE_BENCHMARK.bat`.
The new launcher is an explicit experiment. `recommended_backend_by_candidates`
compares measured p95 and can retain compact when workers are slower. A genuine
comparison mismatch still fails and saves diagnostics before exiting.

## What is different

The existing threaded mode still does Python work under the same GIL. This mode
starts persistent lightweight Python processes so groups of candidate forecasts
can use separate CPU cores. Only the parent loads Torch, the model and CUDA.
Workers import RocketSim, RLGym and NumPy, retain their simulated branch states,
and preload native controls once. Runtime reports include actual worker count
and `worker_torch_loaded` flags.

Contiguous arrays travel over private local binary pipes. No localhost HTTP,
executor files, shared-memory setup or external service is involved. Native
stdout is kept separate from the protocol, and framing handles partial pipe
reads/writes. Failed workers are terminated and reported; timeouts bound waits.
Workers shut down when the planner closes or the benchmark is interrupted.

There is still Python snapshot extraction and inter-process communication. This
is not an all-C++ implementation of the entire forecast. More processes can
increase overhead or memory use instead of improving latency.

## Other worker counts

For a different CPU, repeat with two or six workers:

```bat
REPLAY_IL_MULTICORE_BENCHMARK.bat --device cuda --workers 2
REPLAY_IL_MULTICORE_BENCHMARK.bat --device cuda --workers 6
```

Allowed process counts are 1..8, capped by candidate count. `--workers` controls
simulation processes; `--threads` separately controls Torch CPU threads. Each
invocation replaces the multicore report, so copy it to retain several settings.
The launcher warms both backends twice and measures five calls. Startup/model
compilation and the first call are recorded separately from warmed latency.

Use `--team-size 2` or `--team-size 3` to measure team modes. Kickoff timings and a
few samples do not establish full-match tail latency or competitive strength.
The previous 12-candidate GPU test met 66.7 ms; 64 candidates have not met it.

## Validation

Regression tests cover repeated decisions, both colors, 1v1/2v2/3v3, goal-ending
forecasts, original numerical/physics behavior, partial control chunks, no Torch
in workers, child failure cleanup and partial/corrupted pipe frames. Original
`replay_il/` training source fingerprints and checkpoint/vocabulary checks stay
unchanged. No optimizer, dataset, trained weights or reward targets are changed.

```bat
.venv\Scripts\python.exe -m pytest -q tests\test_replay_inference.py tests\test_replay_runtime.py tests\test_replay_native_runtime.py tests\test_replay_processes.py
```

The cloud has CPU only. Its full-size architecture timing fixture uses random
weights and the supplied action vocabulary, not the trained checkpoint that
exceeds the file tool's transfer limit. Windows/GTX 1650 performance needs the
local comparison above. The package is an inference/backend benchmark, not a
playable adapter for this chunk model.

In a five-call cloud fixture run at 64 candidates, compact measured **286 ms
median / 313 ms p95**, versus **190 ms median / 446 ms p95** with four processes.
Forecast scores and selected action matched. The median improved while the tail
regressed; this is not evidence of a reliable deadline improvement. The report
therefore recommended compact for that budget. No 67 ms result is claimed.

The optional [turbo tuner](README_REPLAY_TURBO.md) adds packed temporal kernels,
bounded CUDA graphs and automatic worker comparisons against this frozen backend.
Run `REPLAY_IL_TURBO_BENCHMARK.bat` to measure those paths on the target PC.
