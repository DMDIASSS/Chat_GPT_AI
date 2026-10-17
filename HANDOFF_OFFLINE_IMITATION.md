# Continuation brief: offline Rocket League action-chunk imitation

This is a ready-to-paste task brief for another coding assistant. The code and
current local reports are authoritative; inspect them before changing anything.

Latest consolidated entry point: `REPLAY_IL_FINAL.bat` / `replay_il_workflow.py`.
Read `REPLAY_FINAL_GUIDE.md` first. It adds fixed replay input snapshots,
total-epoch resume semantics (completed reruns do not add epochs), durable
progress heartbeats, validation-only constant-token/collapse diagnostics and
optional explicitly scripted kickoff assistance. These changes are outside the
fingerprinted `replay_il` package. The old launcher semantics remain available
for compatibility; use the final workflow for the new instructions.

The final workflow now defaults to all 1v1/2v2/3v3 formats, not mandatory 3v3
coverage. Keep the legacy mixed run/dataset names to reuse the existing cached
work. `cache` verifies saved shards without parsing/training. Fresh inputs scan
all of `data/replays`; old snapshots retain their original budgets. The user's
latest log completed 287 inputs with 196,132 samples and 12 rejected replays,
then stopped at the old 3v3 quota. Do not erase/reconstruct those completed
shards. Eight rejections were BoxCars `MissingAttribute` errors; removing the
quota does not make those replays decodable. The parser/trainer hashes remain
unchanged. `--require-3v3` opts back into strict coverage.

## User's current goal and constraints

Continue implementing a small, efficient model inspired by a community claim:
roughly 3.3M parameters, high-level human replays, reconstructed inputs, short
action chunks as tokens, and optional inference-time RocketSim forecasts.
The original community post/implementation URL was not supplied. Its claimed
competitive results are unverified; do not invent a citation or promise equal
strength from parameter count alone.

The user explicitly reaffirmed **offline imitation only**. Do not add PPO, RL,
self-play, teacher-generated demonstrations, generated training matches, reward
shaping, or opponent matches as a new requirement. Validate on real held-out
replays. Short RocketSim reconstruction/forward checks and existing inference
benchmarks are not training matches; generated states must never become replay
training examples. Do not introduce gameplay evaluation unless the user later
asks for it. Do not ask the same offline-vs-RL question again.

The uploaded "Deep Research Mission" is background material. It asks for a broad
RL literature/reward/world-model investigation, but the latest user instruction
keeps this project in imitation learning. Do not spend the implementation budget
producing a speculative 40–60-paper survey. No aerial reward C++ source or flip
energy expression was included in that brief; do not fabricate a review.

Prefer concrete implementation, a small downloadable source update and exact
CMD instructions. The user struggles with full-repository downloads and manual
copying. Preserve private files and avoid repeated approval questions for
authorized reversible work. Never publish model weights, replays, TAS, HAR,
credentials or uploaded logs in the source archive.

## Repository and local data

* Repository: https://github.com/DMDIASSS/Chat_GPT_AI
* Working branch: `codex/native-quality-campaign`.
* Windows project: `E:\Downloads\Chat_GPT_AI`.
* Development checkout: `/workspace/Chat_GPT_AI` when available.
* Python: existing project `.venv`; use its interpreter explicitly.
* Hardware: i5-10300H, GTX 1650 Mobile 4 GB, 16 GB DDR4 2993 MHz.
* User's native runtime: PyTorch 2.14.1+cu126, RocketSim 2.2.1.
* Cloud currently has CPU-only Torch; do not claim GPU tests ran here.
* Inputs: `data/replays/ranked-duels`, `ranked-doubles`, and newly
  `ranked-standard/ranked-3v3-2026-10-15-lwizwie17f`.
* TAS: `data/tas`; audited 66/67 files, 108,461 frames, three center-ball starts.
  TAS controls alone are not synchronized Rocket League state/control labels.
  Never silently treat them as training matches or replace missing states.

There was a pre-existing unrelated edit in
`GigaLearn_Project/Native_Attention/AttentionWorld.h`. Preserve it and do not
stage/package it as part of this work. Its original diff SHA256 was
`155b8ccf2ec99bc35e15d6f9057fa81cae81002ebd27eb5d05ee77c12220b62c`.

## Existing completed model

The fresh `replay_scratch01` run completed ten epochs / 24,450 updates. It used
196,062 examples from 279 replay inputs, with four rejects in its reported
preparation. It was initialized randomly; it did not load Nexto, 271 or cycle
weights. Preserve this run.

* Parameter count: 3,271,683; vocab 256; observation history eight frames at 15 Hz.
* Spatial observation shapes: q `[B,8,1,32]`, kv `[B,8,41,24]`, mask `[B,8,41]`.
* Temporal width 256, four layers, eight heads, FF width 768.
* Token: medoid representing an actual 32-by-8 control sequence at 120 Hz.
* Inputs: ball, up to six cars, boost pads and past controls, using causal history.
* Tokens are short control patterns, not labeled tricks, language words or a
  guarantee of mechanically meaningful segmentation. Complex moves span chunks.
* Vocabulary is fitted on training matches only. Buttons retain exact 0/1 edges.
* Losses: token CE and three bootstrapped supervised next-goal value heads.
* Replay controls are constrained inverse estimates, not authentic hardware inputs.
* Full matches are grouped in 80/10/10 splits, with ID/file-hash deduplication.
  Alternate POV leakage is still possible if reliable internal match IDs are absent.
* Dataset is immutable after preparation. Adding data requires a new dataset/run.
* Training file hashes are pinned for resume: **do not edit `replay_il/*.py` for
  inference changes**. Existing run resume compatibility must remain intact.
* The supplied kickoff book was empty; do not claim a working pro kickoff book.

Selected checkpoint SHA256:
`04aca70d21649ed7e1b90b0a30d411253f286c8c858f3725d2d8cb1741872db4`.
Vocabulary SHA256:
`1263df641607c9a23cb81ee9509b22411c5032509cf4b2ee7df8e8dcc2d48969`.
Private checkpoint may exceed the attachment tool's 32 MiB download cap. Never
pretend a random engineering fixture is the user's actual trained weights.

Held-out report: 18,780 samples; token CE 3.07865, top-1 23.70%, top-5 55.21%,
value MSE 0.218515 vs constant-zero 0.248430, control-chunk MSE 0.169330.
These are offline metrics. Competitive strength is unverified. Test results are
identity-cached and cannot be repeatedly used for checkpoint selection.

## Current optimization implementation

Inspect these inference-only root files:

* `replay_il_runtime.py`: cached spatial features, batched observations/device selection.
* `replay_il_inference.py`: packed cross-attention, final temporal query only,
  in-memory frozen TorchScript.
* `replay_il_native_runtime.py`: compact/native/process forecasts and strict
  candidate-by-token parity comparisons. Forecast horizon 120 ticks; execute eight.
* `replay_il_forecast.py`, `replay_il_snapshot.py`: exact control edges and snapshots.
* `replay_il_processes.py`, `replay_il_cpu_worker.py`, `replay_il_pipe.py`:
  persistent CPU-only children with private framed pipes; workers do not import Torch.
* `replay_il_turbo.py`: explicit packed causal attention, packed value-head
  projections, contiguous/pinned transfers, fixed GPU feature bank and bounded
  CUDA graphs. No compiler, quantization or precision change.
* `replay_il_turbo_benchmark.py`: compare frozen/turbo/graphs at 16/32/64 candidates,
  automatically test 2/3/4 workers, save validated settings in `runtime_profile.json`.

Actual user GTX 1650 measurements, before turbo:

| Four-worker frozen forecasts | Median | p95 |
|---|---:|---:|
| 12 candidates | 48.94 ms | 52.21 ms |
| 16 candidates | 55.90 ms | 58.32 ms |
| 32 candidates | 83.65 ms | 106.49 ms |
| 64 candidates | 146.73 ms | 149.80 ms |

At 64, neural continuation/value took about 71 ms, simulation/snapshots 52 ms.
The target interval is 66.67 ms. These were five warmed kickoff samples, not
full-match tail guarantees. Opponents currently hold last observed controls;
future human actions are unknown. GPU forecasts remain pending for the turbo
update; do not promise 64 candidates meets target.

Cloud full-size random-model/real-vocabulary fixture, two Torch threads:
old frozen/four-worker 64 median 223 ms / p95 256 ms; turbo/two-worker median
189 ms / p95 194 ms. At 16: 74/87 ms versus 54/61 ms. CPU results are not GTX
1650 results. Broader collision validation found small differences for one
worker grouping even with the same frozen network. Reject failing settings;
never widen parity tolerance just to obtain a success message.

CUDA graphs capture only during explicit warmup, with at most six shapes.
Irregular shapes run eager FP32. Actual CUDA capture tests skip on CPU; the
on-laptop tuner checks numerical parity and reports failures/fallbacks.
Existing old launchers retain their previous defaults. No game adapter is
installed by these benchmark commands. A later user request authorized an
RLBot v4 export: `EXPORT_REPLAY_RLBOT.bat` / `export_replay_rlbot.py` now creates
a self-contained policy-only bot with temporal history and exact chunk controls.
See `README_REPLAY_RLBOT_EXPORT.md`. It does not include the RocketSim search
planner, launch a match, retrain, or authorize adding matches to learning.

## Curated 3v3 addition and exact commands

The user's curated group:
https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f

They describe good 3v3 replays using Octane-hitbox cars. This cloud's Ballchasing
HTTP access was blocked. Treat quality/hitbox as user-provided provenance until
verified from actual replay metadata; do not invent ranks or silently force
every car to Octane. `download_3v3_group.py` scopes API pagination to this group,
requires six-player ranked-standard metadata, retains ranks/car IDs/names,
deduplicates IDs/content, resumes pending work and respects persisted cooldowns.
Subgroups are not recursively enumerated.

Run on the user's PC:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
DOWNLOAD_3V3_GROUP.bat
REPLAY_IL_START_3V3.bat
```

The new launcher prepares `dataset_mixed3v3_02`, verifies accepted 3v3 coverage
with `audit_replay_mix.py`, then starts/resumes **fresh** `replay_mixed3v3_02`.
It includes the duels/doubles folders too. Require at least two accepted 3v3
matches in each split; otherwise stop and retain `format_audit.json` evidence.
Parsing can be expensive and stricter all-car fit checks can reject 3v3 chunks.
Do not weaken reconstruction checks or claim a folder count equals usable data.

```bat
REPLAY_IL_PAUSE_3V3.bat
REPLAY_IL_TURBO_BENCHMARK.bat
REPLAY_IL_TURBO_BENCHMARK.bat --run replay_mixed3v3_02
```

The last command requires the new selected model to exist. W&B login and API
support already exist in the supervised trainer. Reuse local credentials,
never copy API keys into code, prompts, logs or public ZIPs. Check
`wandb_state.json`, `events.jsonl`, actual update counts and nonzero parameter
changes. Only validation selects checkpoints; held-out test remains final-only.

## Useful primary links

* Code: https://github.com/DMDIASSS/Chat_GPT_AI
* Branch: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/native-quality-campaign
* Curated 3v3 group: https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f
* Earlier GC3–SSL doubles search: https://ballchasing.com/?playlist=11&min-rank=21&max-rank=22
* API documentation: https://ballchasing.com/doc/api
* Local token acquisition: https://ballchasing.com/upload
* RocketSim: https://github.com/ZealanL/RocketSim
* RLGym Tools replay conversion: https://github.com/RLGym/rlgym-tools
* PyTorch CUDA graphs: https://pytorch.org/docs/stable/notes/cuda.html#cuda-graphs
* PyTorch attention: https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html
* W&B documentation: https://docs.wandb.ai/
* User's earlier reward guide: https://github.com/ZealanL/RLGym-PPO-Guide/
  (background only; `REPLAY_REWARD_DESIGN.md` records the prior review).

These are project/documentation links, not a verified literature review. Check
the current official source before making new API/version claims.

## Immediate next implementation priorities

1. Finish source-update verification/publication; give one small ZIP and exact
   commands. Preserve training fingerprints and the unrelated C++ edit.
2. Run the new acquisition/coverage audit on the user's machine. Inspect actual
   3v3 reconstruction yield, fit errors, format balance and hitbox provenance.
3. Train the separate supervised run. Prove gradients/weight updates occur and
   report held-out imitation/value metrics without claiming wins or skill rank.
4. Measure the new CUDA path locally; select validated latency settings rather
   than maximizing worker counts. Consider further inference changes only when
   a report identifies the remaining bottleneck.
5. If future sequence modeling/tokenization changes are needed, create a new
   explicit dataset/model version. Current shards are reservoir samples and do
   not preserve reliable contiguous player/time identity for long action-token
   sequences; do not pretend arbitrary shuffled rows form a language sequence.
6. Do not turn TAS into demonstrations without synchronized state reconstruction,
   and do not call fixed last-input opponent forecasts learned opponent modeling.

Run the relevant tests, including real supervised optimizer/save/resume checks:

```bat
.venv\Scripts\python.exe -m pytest -q tests/test_replay_inference.py tests/test_replay_runtime.py tests/test_replay_native_runtime.py tests/test_replay_processes.py tests/test_replay_turbo.py tests/test_replay_group_download.py tests/test_replay_mix.py tests/test_replay_imitation.py tests/test_replay_interpolation.py
```

Document actual passed/skipped checks. Do not claim CUDA or authenticated API
tests ran when they did not. Matching the design of a strong community bot is
an engineering hypothesis, not proof that this model has reached that strength.
