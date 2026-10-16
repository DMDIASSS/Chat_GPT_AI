# Native replay planner optimization

Extract this small update into **E:\Downloads\Chat_GPT_AI**, allowing the included
runtime source to replace its previous version. Your existing project, Python
environment and trained replay-imitation run are required.

Run in CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda
```

The result is saved to:

```text
data\isolated\replay_imitation\runs\replay_scratch01\native_runtime_benchmark.json
```

The old `runtime_benchmark.json` remains available for comparison. A different
existing run can be selected with `--run NAME`. Explicit `--device cuda` fails if
CUDA is unavailable; `--device auto` chooses the available device.

## What changed

The preceding GPU report measured about **339 ms** for a full 64-candidate,
one-second search. The desired eight-tick action interval allows **66.7 ms**.

This inference backend reuses RocketSim arenas, steps intervals with
identical controls directly in native code, and extracts observations without
constructing a Python GameState every eight ticks. It preserves every individual
jump, flip, steering and boost transition. At action-chunk boundaries it retains
the preceding planner's state reconstruction behavior. Observation construction
allocates only the controlled player's view, with the same quaternion conversion,
float64 intermediates, team inversion, previous controls and masks used in training.
The shared runtime also gathers cached history features in one tensor operation.

All **64 candidates, the one-second horizon, the value heads and the first eight
executed ticks** remain available. Four- and sixteen-candidate timings are labeled
separately. The benchmark also measures the direct policy, which performs no search.
Neither smaller searches nor the direct policy are assumed equally strong.

This uses the installed RocketSim physics engine, which GigaLearn also uses.
It is **not an all-C++ GigaLearn port**: Python still schedules branches and builds
features, and Torch runs the network. GigaLearn's aggregate training SPS does not
by itself measure latency of an autoregressive planning decision. No PPO, RL or
self-play training is started and no model weights are changed.

## Measurement and settings

By default the benchmark compares the previous runtime with the optimized
runtime at **4, 16 and 64 candidates**, using your real `best.pt` and vocabulary.
It checks that candidate scores, values, uncertainty and selected tokens agree
on the benchmark state. A failed check stops with an error. It reports the first
call separately, then warmed individual samples, median and an estimated p95.
The p95 must meet 66.7 ms before it is labeled as meeting that deadline. CUDA is
synchronized at decision boundaries.
`recommended_backend_by_candidates` identifies the faster measured backend by
p95 for each budget; it can select the reference if native stepping regresses.
This is a benchmark recommendation, not an automatic gameplay configuration change.

Simulation defaults to `--stepping compact`: one reused arena, native held-control
steps, and lightweight snapshots at action-chunk boundaries. This minimizes arena
allocation and memory traffic. Separate arenas and parallel workers are available
as explicit experiments, not guaranteed improvements:

```bat
REPLAY_IL_NATIVE_BENCHMARK.bat --device cuda --stepping workers --workers 2 --repeats 5
```

`--threads 2` controls Torch CPU threads independently. `--stepping workers`
uses one arena per candidate; `--workers 1` runs those sequentially. The optional
`--stepping multi_step` uses the installed wheel's native global worker pool;
some machines suffer from excess worker overhead. Neither setting changes
the search budget. Arenas are warmed and reused within each configuration.
The initial allocation can be substantially slower than subsequent calls.
The report includes phase timings so simulation, observation building and network
inference can be distinguished. In compact mode, chunk state reconstruction is
included in `simulation_and_snapshots`.

Use `--team-size 2` or `--team-size 3` for 2v2 or 3v3 timings, and `--repeats 10`
for a better tail estimate. Repeated seeded kickoff timings do not establish
full-match worst-case latency or playing strength. Each invocation replaces
`native_runtime_benchmark.json`, so copy it first to retain multiple settings.
`--skip-reference` skips reference timings and the on-PC parity check.

## Compatibility and tests

All runtime changes are outside `replay_il/`, preserving its pinned training
source hashes and resume compatibility. The existing checkpoint and vocabulary
hash checks remain active. No weights, optimizer state, datasets, training
progress or held-out results are written. The ZIP contains source and tests only.

Tests compare native physics against individual 120 Hz steps through dense
car/ball contacts and changing jump, steering and powerslide controls. They also
check feature parity for both teams in 1v1, 2v2 and 3v3, including demos, rotations,
ground and flip flags, pad cooldown boundaries and previous actions. Ordinary
and goal-ending forecasts are checked with compact, sequential, bounded-worker and native
global-pool stepping, including repeated decisions on reused arenas.
The dense-contact step test starts from matching cloned collision graphs;
independent arenas can order overlapping contacts differently even when both
use the ordinary engine. Local score parity is checked on the benchmark state,
not asserted for every possible collision configuration.

```bat
.venv\Scripts\python.exe -m pytest -q tests\test_replay_runtime.py tests\test_replay_native_runtime.py
```

The complete CPU comparisons were variable: the native 64-candidate path was
faster in some runs and slower in another. One final compact run measured about
**899 ms reference versus 806 ms compact** (five-call medians); both missed
66.7 ms. These results do not establish a consistent full-planner speedup.

The cloud has no CUDA device, and the uploaded trained checkpoint exceeds the
32 MiB transfer limit. Cloud engineering measurements use the matching 3.27M
architecture with random fixture weights and the supplied action vocabulary.
Run the command above to measure your trained weights on the GTX 1650. A faster
physics microbenchmark does not imply the complete search meets its deadline.

This update is an inference backend and benchmark. It does not add a playable
RLBot or Roblox adapter for this new action-chunk architecture. Your uploaded
kickoff book is empty; no replay-derived kickoff is supplied or claimed.
