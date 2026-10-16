# Replay imitation: turbo inference and automatic worker tuning

Extract this small source update into your existing `Chat_GPT_AI` directory,
replacing matching files. Keep your existing `.venv`, trained run and vocabulary.
In CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_TURBO_BENCHMARK.bat
```

The launcher requests CUDA. It compares the preceding four-worker frozen
backend against the new turbo and CUDA graph paths, testing two, three and four
CPU simulation workers. It measures 16, 32 and 64 candidates with the same
one-second horizon and eight-tick execution interval. Initial compilation,
worker startup and graph capture happen during setup/warmup, outside the warmed
timings. Wait for `COMPLETE`; no extra dependencies or C++/Rust compiler are
required. It uses the installed PyTorch and RocketSim wheels.

The target i5-10300H has four physical cores/eight threads; using eight simulation
processes can compete with the main process preparing GPU inputs. The tuner
measures worker configurations instead of assuming maximum utilization is
fastest. CPU workers load neither Torch nor the model. Only the parent owns the
GPU network. The new configurations use one Torch CPU thread by default;
the preceding baseline retains its two-thread setting.

For a shorter comparison, or different budgets:

```bat
REPLAY_IL_TURBO_BENCHMARK.bat --candidates 64 --workers 3 4
REPLAY_IL_TURBO_BENCHMARK.bat --team-size 2 --repeats 20
REPLAY_IL_TURBO_BENCHMARK.bat --device cpu --networks turbo --threads 2
```

## Changes

* Packed QKV projections and causal scaled-dot-product attention replace the
  general-purpose temporal encoder dispatch. The final temporal layer still
  evaluates only the needed final query.
* The three existing value heads share one packed first-layer matrix multiply;
  each retains its own weights, bias, exact GELU and final tanh.
* CUDA graphs capture spatial encoding, feature-bank updates, history gathers
  and temporal evaluation together. One pinned host transfer supplies contiguous
  observations and indices; feature history stays on the GPU. Graphs replay
  native GPU commands with fewer Python/driver launches.
* Graph storage is bounded to six shapes per planner and a fixed feature bank
  (under 0.5 MiB at 64 candidates). Graph intermediate storage and workspace use
  more VRAM; the report records peak Torch allocated/reserved memory. These
  figures exclude the game and driver. Unsupported/irregular shapes use eager
  FP32 inference, avoiding graph compilation during play.
* Snapshots avoid per-car NumPy trace/transpose temporaries while retaining the
  original double-precision quaternion branch rules, pad cooldown threshold,
  demo pose, ground/flip flags and feature contract.

Physics already runs in C++ RocketSim. These changes keep its exact control
edges, 120-tick forecast and branch-boundary reconstruction. They do not change
trained weights, tokens, training files, precision or model size. There is no
quantization, shortened forecast or hidden candidate reduction. Unicode is a
text encoding and would not accelerate this computation.

## Correctness and saved settings

For each budget, the tuner compares candidate sets, selected actions and every
candidate's score/value/uncertainty against the preceding frozen backend.
At the largest tested budget, it also checks early goals and moving/airborne
states in 1v1, 2v2 and 3v3, including orange-team observations. Differences above
the existing `1e-4` tolerance reject that configuration. Different native arena
reuse/grouping can introduce small collision differences even with the old
network; those failures remain visible and are not hidden by widening tolerance.
Any rejected configuration is excluded at all budgets. Failed CUDA graph capture
also excludes that graph configuration; ordinary turbo/frozen paths remain
available.

Results in `data\isolated\replay_imitation\runs\replay_scratch01\`:

* `turbo_runtime_benchmark.json`: timings, parity diagnostics, GPU memory,
  capture status and recommendations per candidate budget.
* `runtime_profile.json`: matching checkpoint/vocabulary hashes, hardware name,
  and settings for the largest tested candidate count meeting the 66.67 ms
  inference budget. `selected: null` means no tested budget met it. Recommendations
  are still recorded for each candidate count. A validated older backend can
  remain the recommendation if it performs better.

`passed_with_rejections` means the report contains validated recommendations
plus explicitly rejected alternatives. It is not a claim that every path passed.
No setting is installed into a game adapter by this benchmark. It prepares
inference configuration for the existing chunk model; this model still needs a
compatible playable adapter. Existing launchers keep their previous defaults.

Five warmed kickoff samples are a quick comparison, not a full-match latency
guarantee. The inference budget does not include game observation/input latency
or contention from a running game. More candidates are not proof of greater
playing strength. Rocket League forecasts also do not make different Roblox
physics match RocketSim.

## Validation

```bat
.venv\Scripts\python.exe -m pytest -q tests/test_replay_inference.py tests/test_replay_runtime.py tests/test_replay_native_runtime.py tests/test_replay_processes.py tests/test_replay_turbo.py
```

The cloud checks cover complete forecast parity, both colors, early goals,
2/4/6-car rosters, repeated calls, dynamic feature-bank indices, bounded graph
shape reuse and failure exclusion. Actual CUDA capture/replay tests require a
CUDA machine; they skip on this CPU-only cloud environment. GPU performance
must be measured on the target laptop. No GTX 1650 speedup is claimed from CPU
measurements alone.
