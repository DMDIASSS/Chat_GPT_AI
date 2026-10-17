# Replay imitation runtime benchmark

Extract this small source update into **E:\Downloads\Chat_GPT_AI**. It requires
the existing project, Python environment and trained `replay_scratch01` files.
It does not contain a model or download one.

In CMD, run:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_RUNTIME_BENCHMARK.bat --device cuda
```

`--device auto` selects CUDA when available and otherwise CPU. Explicit `cuda`
stops with an error if unavailable; it never silently benchmarks on CPU instead.
The console prints `RUNTIME_DEVICE` and the report records the actual device.
Use `--run NAME` for a different existing replay imitation run.

The result is saved separately from the preceding benchmark:

```text
data\isolated\replay_imitation\runs\replay_scratch01\runtime_benchmark.json
```

## What this fixes

The old `REPLAY_IL_PLANNER_BENCHMARK.bat` route loaded the model on CPU and ignored
its accepted `--device` argument. Its single timing also included cold-start work.
The supplied report took 1,420 ms for 64 one-second candidates, versus a 66.7 ms
budget for the intended eight-tick action interval.

This separate runtime honors device selection, defaults to two Torch CPU threads,
batches observation construction across branch snapshots, and caches spatial
features for repeated history observations. It retains the same full one-second
search, candidate scoring, value heads and first eight executed ticks. The
ordinary 120 Hz simulation engine and controls are unchanged. The simulator
still runs on CPU even when the neural network uses CUDA.

The benchmark compares **direct policy inference**, then **4, 16 and 64 search
candidates**, all explicitly labeled. Direct policy mode selects the model's
highest-probability action chunk without candidate simulation. Smaller search
budgets consider fewer first actions; neither option is assumed equally strong.
The script warms up each mode and measures three calls. CUDA timings synchronize
before and after the measured decision. Each mode reports individual samples,
median, estimated p95 and whether that p95 meets 66.7 ms.

These are repeated 1v1 kickoff-state timings, not full-match worst-case latency
or proof of gameplay strength. Three samples give only a rough tail estimate.
Try more samples with `--repeats 10`. This tool does not connect to RLBot or Roblox
and does not export a playable bot. Match testing needs a separate compatible
adapter for this action-chunk model.

## Preserving your trained model and resume compatibility

All new runtime code is outside `replay_il/`. No existing training, parsing,
model or planner source is replaced. Their pinned training code hashes therefore
remain unchanged. The tool reads your existing `best.pt`, `tokens.npy`,
`selected.json` and `tokenizer.json`; existing checkpoint/vocabulary hash checks
remain active. It never modifies weights, optimizers, datasets or test results.
Only a new `runtime_benchmark.json` report is written into the existing run.

Your uploaded `kickoff_book.json` is empty, so no replay-derived kickoff book is
claimed. A random or arbitrary substitute kickoff is not silently added.

## Verified here

Eight tests cover exact batched observation parity for both colors in 1v1,
2v2 and 3v3; cached history inference; ordinary and goal-ending search parity;
explicit CUDA/device handling; checkpoint loading and latency report fields;
and preservation of all original training-source hashes.

With matching 3.27M-parameter **random fixture weights** and the supplied action
vocabulary, three warmed 64-candidate CPU timings had a median of approximately
**1,250 ms before and 515 ms after**. Candidate tokens/scores and the selected
action matched. Five direct-policy calls had a median near **3 ms**. These
numbers are engineering fixtures, not a test of the trained model's strength.
The 64-candidate CPU path still misses the 66.7 ms deadline.

The cloud has no CUDA device. The supplied trained `best.pt` exceeds the file
tool's 32 MiB transfer limit, so that exact checkpoint could not be run here.
The new local benchmark measures your actual trained model and GPU on your PC;
no GPU speed or playable real-time search result is promised in advance.

Run the runtime tests using the existing environment:

```bat
.venv\Scripts\python.exe -m pytest -q tests\test_replay_runtime.py
```
