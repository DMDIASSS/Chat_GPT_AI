# Continue my Rocket League replay-imitation bot

Copy this document into the new AI conversation. It is a project handoff and
actionable prompt, current as of **2026-10-17**. Inspect current code and actual
reports before treating historical measurements as current results.

## 1. What I want you to do

Continue developing the existing project. First diagnose why the replay-trained
RLBot sometimes stays idle, circles, rarely boosts outside kickoff and appears
not to jump. Distinguish learned-policy weakness from label/tokenization errors,
export differences, live observation differences and deployment timing. Then
implement and test the smallest evidence-backed improvement.

Use the repository and execution tools directly. Do useful inspection and run
the available checks before responding with a long plan. Reuse existing
implementations and caches. Do not rebuild the whole project or ask for links
already supplied here. Make routine engineering decisions autonomously, keep
working checkpoints safe, and report what actually ran. Give concise progress
updates and exact Windows CMD commands when a check must run on my computer.

Deliver runnable changes, relevant test results, limitations and a small
standalone source-update ZIP when appropriate. I prefer downloading an update
folder to repeatedly downloading the entire repository. Do not claim that tests
with synthetic fixtures prove my private trained model plays well.

## 2. Scope and constraints

- **Training is purely offline human-replay imitation.** No PPO, reinforcement
  learning, self-play, teacher-generated training games, reward shaping or
  search-generated training labels. Do not load 271/Nexto weights as the base.
- Supervised value labels may use outcomes from human replays. Actor inputs
  must not contain future outcomes. RocketSim inverse reconstruction, short
  physics checks and inference-time forecasts are allowed; these are not
  policy training matches.
- RLBot deployment/manual games are already part of this project. Do not feed
  those games into training. Current priority is diagnosing the existing bot,
  not launching a large competitive evaluation campaign from an old template.
- Use all supported **1v1, 2v2 and 3v3** replay formats. Missing 3v3 coverage must
  not block otherwise valid duels/doubles training by default. Reserve whole
  validation/test matches; “use every replay” does not mean train on test data.
- Preserve raw replays, accepted chunks, datasets, tokens, checkpoints, optimizer
  state and working exports. Do not delete caches to make progress counters look
  clean. Explain a genuine need for new reconstruction/versioning before doing it.
- Do not force random jumps, constant throttle/boost, or movement heuristics and
  present the resulting behavior as a better learned model. Basic scripted
  kickoff assistance already exists and must stay explicitly identified.
- Do not publish private weights, replays, logs, HAR/TAS captures, account launch
  details or API credentials. Source updates must use an explicit file whitelist.
- The older project includes Roblox/JJSploit, browser extensions, TAS, PPO,
  native-attention campaigns and many other experiments. Those are historical;
  do not resume them unless I explicitly request that scope.

## 3. Repository, exact baseline and documentation

- Repository: https://github.com/DMDIASSS/Chat_GPT_AI
- Active branch: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/native-quality-campaign
- Known source baseline for the latest runtime diagnostics:
  https://github.com/DMDIASSS/Chat_GPT_AI/tree/4c45deadc39508459a1b69a4b6018f878453c89f
- Full current workflow guide:
  https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/REPLAY_FINAL_GUIDE.md
- Jump/boost/export diagnostic guide:
  https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_CONTROL_CHECK.md
- All-format/cache guide:
  https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_ALL_FORMATS.md
- RLBot export guide:
  https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_RLBOT_EXPORT.md
- Historical engineering handoff:
  https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/HANDOFF_OFFLINE_IMITATION.md

The branch can contain newer changes. Inspect `git log`, `git status` and any
`AGENTS.md` instructions. This document supersedes stale instructions in older
handoffs that describe mandatory 3v3 coverage as the default.

Latest standalone source update, including the all-format workflow and control
diagnostics, but **no private weights or replay data**:

https://github.com/DMDIASSS/Chat_GPT_AI/raw/4c45deadc39508459a1b69a4b6018f878453c89f/downloads/Replay_Control_Check_Update.zip

That ZIP is an update for an existing checkout with its dependencies. It is not
a complete new installation or a trained model download.

## 4. My machine and access limitations

Windows project: `E:\Downloads\Chat_GPT_AI`.

Hardware: i5-10300H laptop CPU, GTX 1650 Mobile 4 GB VRAM, 16 GB DDR4 RAM, roughly
2993 MHz reported. Quiet/power mode affects speed. Do not assume maximum worker
count gives maximum sustained performance on a thermally limited laptop.

Training uses `.venv\Scripts\python.exe`. Previously reported versions include
PyTorch `2.14.1+cu126` and RocketSim `2.2.1`; verify the actual current environment
and saved protocol instead of blindly upgrading packages. W&B support and local
login already exist. The RLBot Python interpreter can be different from this
training environment: the supplied live log selected **CPU**, even though the
training environment has CUDA.

The previous cloud checkout was `/workspace/Chat_GPT_AI`, with a CPU-only Torch
environment. A fresh AI session must inspect its own resources. A cloud agent
cannot read my Windows `E:` drive just because it has the repository. GitHub
contains code, not necessarily my ignored private data. Do not pretend otherwise.

In the previous shared cloud checkout there was an unrelated, pre-existing edit
to `GigaLearn_Project/Native_Attention/AttentionWorld.h`. Preserve it; never stage
it as part of replay work. Its diff SHA256 was:
`155b8ccf2ec99bc35e15d6f9057fa81cae81002ebd27eb5d05ee77c12220b62c`.

## 5. Current data, runs and saved progress

| Purpose | Path relative to the Windows project |
|---|---|
| All replay inputs | `data\replays\` and its subfolders |
| Original duels | `data\replays\ranked-duels` |
| Original doubles | `data\replays\ranked-doubles` |
| Curated 3v3 | `data\replays\ranked-standard\ranked-3v3-2026-10-15-lwizwie17f` |
| Original completed dataset | `data\isolated\replay_imitation\dataset01` |
| Original completed run | `data\isolated\replay_imitation\runs\replay_scratch01` |
| Current all-format dataset | `data\isolated\replay_imitation\dataset_mixed3v3_02` |
| Current all-format run | `data\isolated\replay_imitation\runs\replay_mixed3v3_02` |
| Original tested RLBot export | `data\rlbot_exports\ReplayDuelsDoubles` |

The `mixed3v3` names are retained for compatibility/cache reuse. They do **not**
mean the current final workflow accepts only 3v3.

Original completed run: 279 replay inputs, four rejects, **196,062 accepted
examples**, 10 completed epochs, 24,450 updates. Earlier counts of “220 replays”
in draft prompts are stale. This run started from random weights.

Latest preparation log: **287 replay inputs, 196,132 accepted samples, 12
rejections**. It finished parsing and then stopped at the old strict 3v3 audit.
The new workflow removed that default blocker and reuses `manifest.json` and
saved `.npz` shards. Four rejects lacked verified chunks; eight failed the replay
reader with BoxCars `MissingAttribute` errors. The format-policy fix does not
decode those eight files or prove that accepted 3v3 training data now exists.

The user was most recently told how to resume this all-format run. Its current
training progress and the output of the newest control checks are **unknown**
until you inspect fresh reports. Do not assert that it has finished training.

Saved data meanings:

- `shards\*.npz`: reconstructed observations and 32-tick control chunks.
- Matching shard `.json`: source/group/split/configuration/hash metadata.
- `manifest.json`: completed immutable dataset and selected shard records.
- `parse_progress.json`: durable input counts and rejection evidence.
- `input_snapshot.json`: frozen replay input list/content identities/budgets.
- `tokens.npy`: action dictionary fitted during training, not all parsed chunks.
- Token-label `.npy` caches depend on that particular dictionary hash.

Completed manifests skip parsing. Partial preparation reuses shards only when
their configuration and hashes match. New downloads are not silently appended
to a completed experiment. The new default discovers all nested `data\replays`
folders up to the parser's 100,000-input limit; explicit sample budgets and
quality filtering still apply. Old snapshots retain their original budgets.

## 6. Model that actually exists

Original selected artifacts:

```text
E:\Downloads\Chat_GPT_AI\data\isolated\replay_imitation\runs\replay_scratch01\best.pt
E:\Downloads\Chat_GPT_AI\data\isolated\replay_imitation\runs\replay_scratch01\tokens.npy
```

- **3,271,683 parameters**, all trainable, initialized randomly.
- 256 discrete medoid control chunks; **not VQ-BeT, residual VQ or text tokens**.
- Each token is a real 32-by-8 reconstructed control sequence at 120 physics Hz.
- Control order: throttle, steer, pitch, yaw, roll, jump, boost, handbrake.
- The first five values are continuous controls; the last three retain 0/1 edges.
- Eight causal observation frames at a nominal 15 Hz, roughly half a second.
- Spatial attention encoder, temporal width 256, four layers, eight heads,
  feedforward width 768, and three supervised value heads.
- Input shapes `[B,8,1,32]`, `[B,8,41,24]`, `[B,8,41]` for query, entities, mask.
  Padded players are masked with additive `-10000`, not positive `1`.
- Inputs include ball, up to six cars, boost pads and previous controls using
  team-normalized features. Reusing a Nexto-era observation format does not
  mean its pretrained weights or teacher outputs were used in this run.
- Training loss combines token cross-entropy and bootstrapped value-head MSE.
- The current code assigns value zero when `next_scoring_team` is unavailable;
  otherwise team-relative sign times `exp(-max(0, episode_seconds_remaining)/15)`.
  Audit the converter's exact field semantics and missing/truncated outcomes
  before claiming this is a perfectly calibrated time-to-next-goal target.

Vocabulary fitting uses training matches only. Match/group splits are 80/10/10,
with deduplication by content and available match identity. Missing reliable
internal match IDs can still leave alternate-upload leakage to investigate.

Original best checkpoint SHA256:
`04aca70d21649ed7e1b90b0a30d411253f286c8c858f3725d2d8cb1741872db4`.

Matching dictionary SHA256:
`1263df641607c9a23cb81ee9509b22411c5032509cf4b2ee7df8e8dcc2d48969`.

The completed run's held-out report: 18,780 samples; token CE 3.07865, top-1
23.70%, top-5 55.21%, value MSE 0.218515 versus constant-zero 0.248430, and
control-chunk MSE 0.169330. These measure offline prediction, not competitive
strength. Do not tune repeatedly against this already-used final test.

`best.pt` is validation-selected; `latest.pt` contains resumable training state.
The matching dictionary/protocol are essential. An unrelated `actor.pt` plus
`actor_optimizer.pt` uploaded earlier was a Necto/EARL actor and Adam training
state, not this imitation run. Do not substitute those files.

## 7. Current RLBot behavior and diagnosis

The deployed export is RLBot **v4**, standard Soccar, at most six cars. It uses
**direct policy inference**, retaining temporal history, selecting an argmax
token and executing its first eight ticks before replanning. It does **not**
currently include the one-second RocketSim search planner.

Packet-derived ground/jump/flip timers are estimates. Goal posts, field physics
and hitboxes are not magically learned from screenshots or imported meshes.
The boost-pad wrapper matches standard pad X/Y positions and retains canonical
training feature heights; the earlier full-3D anchor check caused a startup
failure and has been repaired.

Optional basic scripted kickoff drives/steers/boosts, yields to a closer teammate,
and hands back control after ball movement or a timeout. It is not a learned
pro kickoff book. The original replay-derived kickoff book was empty.

Latest user report: sometimes AFK/circling, occasional useful defensive touches,
very little boost outside kickoff and no observed jumping. Supplied live log:

- Model loaded as `ReplayDuelsDoubles`, device `cpu`, no model-paused error.
- 76 sampled policy outputs at five-second intervals: zero sampled jump presses,
  one sampled boost press. Short presses between samples could have been missed.
- Token 14 appeared 22 times; its saved controls have zero throttle and nearly
  full steering, with no jump/boost. This explains the issued command, not why
  the network selected it.
- Matching vocabulary has jump in the executed first eight ticks of 50 tokens,
  boost in 71 tokens; over the full 32 ticks, 64 and 100 respectively. These
  controls exist, but token availability does not prove the policy chooses them.

New diagnostics were implemented and published, but their outputs from the
user's actual model/PC have **not yet been supplied**:

1. `CHECK_REPLAY_DUELS_DOUBLES.bat` repairs only the export wrapper, then compares
   the matching actual export and original trained model on 512 cached validation
   samples on CPU. It reports raw reconstructed, tokenized-target and predicted
   jump/boost/slide rates, first-eight versus full-chunk behavior, tokenizer
   retention and numerical/argmax parity. It never reparses or retrains.
2. The updated wrapper counts every callback's issued button values, separating
   learned policy, scripted kickoff and neutral controls. It records inference
   latency, decisions over 66.7 ms, packet gaps and history resets after gaps
   exceeding 16 ticks in `CONTROL_DIAGNOSTICS.json` inside the export.
3. That live file identifies `car_index`; when several cars share a folder it
   holds the latest writer's counters, not a merged team total. Pressed-command
   counts do not prove in-game effects when boost/flip availability or callback
   rate prevents them. Pauses can also produce timing gaps.

First distinguish missing demonstrations, quantization loss, policy underprediction,
deployment input differences, delayed inference and closed-loop distribution
shift. An incorrect action can create unfamiliar states and keep the bot stuck.
Do not assume “let it train longer” or “larger model” is the diagnosis. The
export does not learn while playing. More epochs need validation evidence.

## 8. Critical source files and compatibility safeguards

| Area | Files |
|---|---|
| Final entry point | `REPLAY_IL_FINAL.bat`, `replay_il_workflow.py` |
| Frozen preparation wrapper | `replay_il_prepare_snapshot.py` |
| Cached reconstruction | `replay_il/data.py` |
| Tokens/model/supervised training | `replay_il/tokens.py`, `model.py`, `train.py`, `monitor.py` |
| Validation/button/export checks | `analyze_replay_policy.py`, `CHECK_REPLAY_DUELS_DOUBLES.bat` |
| RLBot export/repair | `export_replay_rlbot.py`, `repair_replay_rlbot.py` |
| RLBot packet/control wrapper | `replay_rlbot_core.py`, `replay_rlbot_agent.py` |
| Packet feature contract | `vendor/nexto/nexto_obs.py`, `afk_team_research.py`, `nexto_teacher.py`, `slater_versatile_data.py` |
| Data coverage audit | `audit_replay_mix.py` |
| Downloaders | `download_2v2_gc3_ssl.py`, `download_3v3_group.py` |

**Training fingerprints are pinned.** Changing or even adding `.py` files in
`replay_il/`, or modifying `afk_team_research.py`, `nexto_teacher.py` or
`slater_versatile_data.py`, can invalidate existing resume protocols. The recent
workflow/runtime fixes were deliberately outside those files. Do not delete or
edit identity checks to bypass a mismatch. If learning/tokenization must change,
create a clearly versioned experiment while preserving the original run and data.

Current chunks are reservoir samples. They do not preserve reliable long-range
player/time identity for stitching arbitrary rows into an LLM-like sequence.
Existing per-example eight-frame histories are causal, but shuffled samples are
not consecutive mechanics. Longer action-token training needs genuine sequence
metadata and a versioned dataset; do not fake continuity. Reuse raw cached chunks
for compatible diagnostics/tokenizer experiments before proposing expensive
new replay reconstruction.

## 9. Inference search and optimization already implemented

Do not rewrite an engine before profiling. RocketSim already performs core
physics in compiled native code. Existing inference-only root modules include:

- `replay_il_runtime.py`: cached spatial features, batched inference/observations.
- `replay_il_inference.py`: FP32 packed cross-attention, final temporal query,
  frozen TorchScript encode/decode.
- `replay_il_native_runtime.py`, `replay_il_forecast.py`, `replay_il_snapshot.py`:
  forecasts, exact control edges and compact snapshot helpers.
- `replay_il_processes.py`, `replay_il_cpu_worker.py`, `replay_il_pipe.py`:
  persistent CPU-only simulation workers with private framed pipes.
- `replay_il_turbo.py`, `replay_il_turbo_benchmark.py`: packed attention/value
  heads, bounded CUDA graph shapes, transfers, local automatic configuration
  comparison and parity checks. GPU capture remains unverified in CPU-only cloud.

The forecast path has used a one-second/120-tick horizon and executes the first
eight ticks, with candidate continuation/value scoring. Other players currently
hold last observed controls; this is not learned opponent behavior and future
human inputs are unknown. Validate actual code, candidate scores and horizon
before describing it as identical to a community design.

User's earlier GTX 1650 measurements with four simulation workers/frozen network:

| Candidates | Median ms | p95 ms |
|---:|---:|---:|
| 12 | 48.94 | 52.21 |
| 16 | 55.90 | 58.32 |
| 32 | 83.65 | 106.49 |
| 64 | 146.73 | 149.80 |

Budget: 66.67 ms per eight physics ticks. At 64 candidates, continuation/value
network was about 71 ms and simulation/snapshots about 52 ms. Five warmed
kickoff repeats are not full-game tail-latency evidence. Game contention matters.
Do not promise 64 candidates will meet budget on this laptop. New turbo local
results remain pending. CPU random-model fixtures are not measured GPU results
or evidence about my trained model's strength.

Packing kernels once caused near-tie candidate order changes; comparisons now
match candidates by token and check scores/value/uncertainty and selection.
Never relax parity tolerances merely to print a pass. Parallel collision
grouping can also change forecasts; reject failing settings.

## 10. Claims from the inspiration/templates versus our implementation

The inspiration was described as replay-only imitation, a tiny roughly 3.3M
model, action chunks/tokens, learned replay-outcome value estimates, about 64
candidate moves with roughly a second of RocketSim forecasts, and a fast pro
kickoff book. This is a design motivation, not independently verified strength.

The conversation described roughly 3,000 high-level replays. Two older uploaded
prompt templates instead mention 220 local replays, a 20,000-replay community
dataset, VQ-BeT with four residual codebooks of 64 entries and continuous offsets,
RocketSim V3, 128-tick rollouts and 50–60 ms CPU search. These are conflicting or
unverified template claims, **not established facts or features of our code**.
No original implementation/results link was provided. Do not invent one.

Keep the useful template ideas: inspect available infrastructure, reconstruct and
verify real demonstrations, split whole matches, compare against simple action
baselines, diagnose failures, measure value usefulness before increasing search,
and use inexpensive controlled experiments. Consider a versioned multimodal
representation only when the data/diagnostics justify it. Do not blindly train a
large VQ architecture, add RL, or assume parameter count reproduces another bot.

## 11. Exact current Windows commands

Run in CMD under `E:\Downloads\Chat_GPT_AI` after installing the source update.

Check the original deployed duels/doubles bot:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
CHECK_REPLAY_DUELS_DOUBLES.bat
```

Equivalent general commands for a matching export:

```bat
REPLAY_IL_FINAL.bat repair --folder data\rlbot_exports\ReplayDuelsDoubles
REPLAY_IL_FINAL.bat analyze --run replay_scratch01 --export-folder data\rlbot_exports\ReplayDuelsDoubles --device cpu --analysis-samples 512
```

Check cached all-format data, then start/resume the current run:

```bat
REPLAY_IL_FINAL.bat cache
REPLAY_IL_FINAL.bat status
REPLAY_IL_FINAL.bat start --device cuda
```

Safely pause from a **second CMD**, then wait for the first training/preparation
window to reach its save boundary and return before closing it:

```bat
REPLAY_IL_FINAL.bat pause
```

Resume with the same start command. Partial parsing may repeat the interrupted
replay; safely paused training resumes a partial epoch from its start with saved
model/optimizer state, so some examples can repeat. Counters restarting while
checking cached shards do not mean that completed reconstruction was lost.

Epoch targets are **total**, not extra epochs per launch. After a completed
10-epoch budget, `start --device cuda --epochs 20` requests a total of 20. It
does not override early stopping after four stale validation epochs. This is
an available command, not evidence that extra epochs improve the model. To
resume the original run explicitly, include `--run replay_scratch01`; the
default run is the separate all-format one.

Inspect/export the original completed best:

```bat
REPLAY_IL_FINAL.bat results --run replay_scratch01
REPLAY_IL_FINAL.bat export --run replay_scratch01 --name ReplayDuelsDoubles2 --scripted-kickoff
```

Inspect/analyze/export the current all-format run once it has selected a model:

```bat
REPLAY_IL_FINAL.bat results
REPLAY_IL_FINAL.bat analyze --device cuda
REPLAY_IL_FINAL.bat export --name ReplayAllFormats --scripted-kickoff
```

Load `data\rlbot_exports\<name>\bot.cfg` in **RLBot v4**. Existing export folders
are preserved; choose a new name for changed weights. Repair preserves the
existing kickoff setting unless explicitly enabled. Runtime `device=auto`
cannot enable CUDA if RLBot's own Torch installation has no CUDA support.

Use `REPLAY_IL_FINAL.bat`, not the legacy `REPLAY_IL_START_3V3.bat`, for current
all-format behavior. The older explicitly 3v3 launcher still enforces its quota.
W&B already works through the trainer; reuse local login and check
`wandb_state.json`. Never request that I paste an API key into chat.

## 12. Evidence, tests and immediate next work

Previous checks, not a blanket statement about future code:

- Consolidated workflow/export/runtime suite: 160 passed, two skipped.
- All-format/cache/download update: 81 passed, one skipped.
- Latest button/timing/export diagnostic changes: **27 passed** in
  `tests/test_replay_rlbot_export.py` and `tests/test_replay_workflow.py`.
- Those latest tests include actual TorchScript export/reload, model/output
  comparison on engineering fixtures, deliberate mismatch detection, short
  jump/boost/handbrake pulses through the wrapper, save/resume and preservation
  of source weights and cached chunks. The RLBot external interface is stubbed
  in cloud tests; no real Rocket League match or CUDA test ran there.
- Authenticated Ballchasing downloads and the newest diagnostics on my actual
  private model still require local evidence. Do not label them completed.

Run relevant tests after changes with the available project interpreter, e.g.:

```bat
.venv\Scripts\python.exe -m pytest -q tests/test_replay_rlbot_export.py tests/test_replay_workflow.py
```

Other relevant suites: `test_replay_imitation.py`, `test_replay_interpolation.py`,
`test_replay_mix.py`, `test_replay_group_download.py`, `test_auto_duos_download.py`,
`test_replay_inference.py`, `test_replay_runtime.py`, `test_replay_native_runtime.py`,
`test_replay_processes.py`, `test_replay_turbo.py` under `tests/`. Use meaningful
checks for the changed behavior. State passed/failed/skipped/GPU-unrun separately.

Your first useful actions:

1. Inspect the current branch, private-data availability and newest reports.
2. Read the two control-check JSON reports if provided. If the actual model is
   locally accessible, run the diagnostic yourself. Otherwise provide the one
   local command, while continuing independent source inspection/tests.
3. Compare raw reconstructed button coverage, tokenized coverage and predicted
   coverage. Check actual export parity, live command counts and timing before
   recommending more epochs or another architecture.
4. If predictions are biased, inspect action class imbalance, conditional
   accuracy and quantization retention; if timing fails, fix deployment first;
   if live inputs differ, reproduce packet/feature parity for that situation.
5. Make one measured, versioned improvement. Preserve existing resume capability
   and reuse compatible chunks. Explain exactly what remains uncertain.

## 13. Which files I should provide to a new AI

### Usually sufficient to start: code access plus small reports

This Markdown and repository/branch access are enough for code inspection. A
full chat export is **not required**. The most useful fresh attachments are:

1. `data\isolated\replay_imitation\runs\replay_scratch01\validation_diagnostics.json`.
2. `data\rlbot_exports\ReplayDuelsDoubles\CONTROL_DIAGNOSTICS.json`.
3. For the current training run: `progress.json`, `selected.json`, `model.json`,
   `protocol.json`, `tokenizer.json`, `wandb_state.json`, latest `epoch_*.json`,
   `results_summary.json` if present; a short recent `events.jsonl` excerpt.
4. For cache/parser questions: dataset `manifest.json`, `parse_progress.json`,
   `input_snapshot.json`, `format_audit.json` and one matching shard metadata
   `.json`. The manifest can be sizable; share only what the task needs.

Do not confuse the completed original run's reports with the new all-format
run. Preserve relative folder names when sharing files with identical names.
Fresh diagnostics matter more than old screenshots or hundreds of chat turns.

### Only when the AI must execute the exact private model

For exported inference: provide the **matching export folder**, including
`policy.pt`, `tokens.npy`, `EXPORT_INFO.json`, `runtime.json`, `bot.py`,
`replay_rlbot_core.py`, `replay_nexto_obs.py`, `bot.cfg`, requirements/license files
and any generated diagnostics. Preserve filenames and directory structure.

For training/model diagnostics: provide the matching `best.pt`, `tokens.npy`,
`selected.json`, `tokenizer.json`, `model.json`, `protocol.json` and relevant
reports. Resuming actual training also needs `latest.pt` with optimizer/RNG state
and the identical prepared dataset, metadata, protocol-compatible code and
dependencies. `best.pt` alone is not enough to reproduce a full training run.

Some checkpoints exceed an attachment tool's 32 MiB download limit. Prefer
connecting a workspace containing them or running the diagnostic locally and
sharing its report; the smaller frozen export may be sufficient for inference.
Do not repeatedly ask for oversized checkpoints before checking whether reports
and source are enough. Use safe loading (`weights_only=True` where applicable);
do not execute arbitrary code from reference archives.

### Only for reproducing reconstruction or sequence-data problems

Provide one or a few affected `.replay` files, their relevant metadata/error
report, and/or representative cached `.npz` shards with matching metadata. The
whole replay collection is unnecessary for an initial diagnosis. Training on a
full private dataset requires actual filesystem access or deliberate dataset
transfer; a Windows path pasted into chat is not access.

Do not upload `.venv`, W&B/API keys, `.netrc` credentials, authorization-bearing
HAR files, session tokens, full Epic launch command lines or unfiltered account
logs. A sanitized relevant chat excerpt is optional; do not upload the entire
chat merely to supply context already recorded here. Old TAS/reference bot
archives and unrelated `actor_optimizer.pt` are not required for this task.

## 14. External links and what each is for

- Curated 3v3 group (user-provided quality/Octane-hitbox claim, not independently verified):
  https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f
- GC3–SSL ranked doubles search:
  https://ballchasing.com/?playlist=11&min-rank=21&max-rank=22
- Ballchasing API and token information:
  https://ballchasing.com/doc/api and https://ballchasing.com/upload
- RocketSim: https://github.com/ZealanL/RocketSim
- RLGym replay tools: https://github.com/RLGym/rlgym-tools
- RLGym: https://github.com/lucas-emery/rocket-league-gym
- RLBot v4 Python framework: https://github.com/RLBot/RLBot
- RLBot documentation: https://wiki.rlbot.org/
- Reference bot pack: https://github.com/RLBot/RLBotPack
- W&B documentation: https://docs.wandb.ai/
- Torch attention documentation:
  https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html
- Torch CUDA graph documentation:
  https://pytorch.org/docs/stable/notes/cuda.html#cuda-graphs
- Earlier user-supplied reward guide, **background only, not a request to add RL**:
  https://github.com/ZealanL/RLGym-PPO-Guide/

The downloader follows API pagination, skips saved IDs/content and respects
persisted cooldowns. Group subgroups are not recursively enumerated. A bug that
mistook a binary replay's first `{`/`<` header byte for JSON/HTML was fixed; actual
error documents remain rejected. Verify authenticated downloads on the user's
machine; previous cloud Ballchasing access was blocked. Never invent successful
downloads, parser support, player ranks, car hitboxes or competitive results.

**Start with the actual diagnostics and current repository. Preserve the work
already done, fix the largest demonstrated problem, and show the evidence.**
