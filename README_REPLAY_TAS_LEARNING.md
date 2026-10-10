# AFK Improved v2.2 — Replay + TAS Learning (guarded experimental release)

**Install:** extract this ZIP into `E:\Downloads\Chat_GPT_AI`, allowing `afk_improved_app.py` to be replaced. Do **not** remove `data`, `vendor`, your `.venv`, or any `.pt` checkpoint. This is an add-on to the existing project, not a standalone Rocket League trainer.

Start the normal desktop app with `AFK_IMPROVED_DESKTOP.vbs`, then open **Replay + TAS Learning**. Or run `LEARN_ONE_CLICK.bat` from the project folder. **Stop your regular PPO / AutoLeague job before beginning replay imitation or final verification.** Replay downloads may remain active, but new downloads will only be picked up on the next dataset build.

## What actually works

1. Audit TAS `.data` recordings (structural checks, SHA-256, raw input-field ranges) and fix the wildcard parsing issue in the earlier inspector. These files are NOT training-ready without verified state/timing/input mapping.
2. Read unique 1v1 `.replay` files using `rlgym-tools` and convert to RLGym v2 states and **approximate** human controls. Skip non-1v1, interpolated/stale or demoed states. Map into the 90-action native Nexto lookup only when physical action feasibility and weighted closest-action confidence agree.
3. Build **native** (`q: N×1×32`, `kv: N×37×24`, `mask: N×37`) training examples. Enforce duplicate filtering, a per-replay cap, category balancing, and a reproducible replay-level train/validation split. Persist each parsed replay to a cache; stop/resume at replay boundaries without reparsing complete files.
4. Conservative imitation learning on a **copy of Cycle 9** using tiny learning rates, gradient clipping, frozen Cycle 9 action-distribution anchoring, validation-based early stopping and policy-drift limits. Frozen reference logits are cached. Stop on nonfinite loss, unexpectedly high divergence or training regression.
5. Run a **separate read-only RocketSim competition**: replay candidate vs original Nexto, Cycle 9 vs original Nexto, and replay candidate vs Cycle 9. Store a verdict. **No automatic promotion**, even if the imitation loss decreases.

**Not implemented:** physically faithful TAS training, human-level controller labeling, TAS-state/action alignment, 1v2/3v3, RLBot v5, GPU-compatible native Nexto TorchScript, guaranteed continuous skill improvement, or "learning" from TAS without observed game states. Never interpret an offline replay-imitation score as a match win rate.

## One-click guide

1. Ensure replay files are in `data\replays\` and TAS `.data` files, if any, in `data\tas\` (create that folder if needed).
2. `LEARN_0_PREFLIGHT.bat` checks the software environment and the protected Cycle 9 checkpoint.
3. `LEARN_ONE_CLICK.bat` audits TAS files (if any), builds/resumes native replay datasets, fine-tunes an isolated model and verifies it competitively. You can also use the app's **One-click: build → train → verify** control.
4. Watch console/app output. Replays may take a while to parse. Use **Request safe pause**. The builder saves each replay to `data\afk_improved\learning\replay_cache` and pauses **between** replays; training pauses **between** epochs.
5. Upload `data\afk_improved\learning\dataset_manifest.json`, `training_report.json`, and `reports\competition_*.json` (or use `LEARN_PACKAGE_REPORTS.bat`) so we can decide whether to run more PPO. Do not promote merely because replay validation improved.

Use `LEARN_CLEAR_PAUSE.bat` to clear a prior pause request **only after the learner has exited**. A second click on one-click reuses a SHA-verified completed dataset/model/evaluation. It does not silently overwrite or restart them. Explicit `--replace` and `--replace-candidate` options preserve archival copies before replacement, but avoid them unless you have a reason.

## Separate commands

```powershell
.\.venv\Scripts\python.exe afk_replay_tas_learning.py tas-audit "data\tas\*.data"
.\.venv\Scripts\python.exe afk_replay_tas_learning.py build "data\replays"
.\.venv\Scripts\python.exe afk_replay_tas_learning.py train
.\.venv\Scripts\python.exe afk_replay_tas_learning.py verify --games 200
```

The old `report.json` containing `[Errno 22] Invalid argument: data\\tas\\*.data` recorded no TAS files. The importer now expands wildcards itself. `tas-audit "data\tas"` works too.

## Performance / safety design

- RLGym Tools conversion can be expensive; parsed, validated replay shards are cached under a key derived from the replay checksum, action table and filtering configuration.
- Frozen Cycle 9 logits are cached once for each dataset checksum, avoiding an extra policy forward pass on every training epoch.
- Training uses `CPU`: original native Nexto TorchScript includes CPU tensors and is not currently CUDA-safe.
- Reconstructed controller inputs remain imperfect despite our filters; rare/difficult cases may be mislabeled.
- Only high-confidence controls are accepted; all decisions are **individual frames**, not exact long-horizon human strategies.
- Replay-level splits prevent the same game's adjacent frames appearing in both training and validation.
- Category balancing caps minority-category weight to 3×. **No bonus/reward hacking** is introduced here; the module uses supervised demonstrations rather than manipulating PPO rewards.
- Validation KL(source||candidate) <= 0.03 and action agreement >= 80% are experimental drift limits, **not guarantees** the candidate remains within 2–3% of the source's skill.
- Only a competitive evaluation against Nexto and the source checkpoint can indicate whether it is worth more PPO work.
- Model checkpoints are stored at `data\afk_improved\learning\replay_candidate.pt`, not `data\autoleague\champion.pt` or Cycle 9.
- `training_report.json` is written after every complete epoch and again on completion.
- A `learning.pause` flag requests a safe exit. Avoid killing the process during a checkpoint write.

## What about TAS inputs?

Your example `.data` files appear to contain an 8-byte header, 32 bytes per recorded frame, and a 128-byte trailer. However, decoding their field meanings or reproducing their starting states in RocketSim has **not** been validated. Input sequences by themselves are not observations: a native Nexto policy needs to know where its car and the ball are at each control decision. The TAS audit therefore does not feed the action sequence to the learner.

To enable TAS imitation safely, we first need a physics-verified capture tool that records **per-frame game state, exact controls, and frame timing**, plus an adapter that maps the full input sequence to Nexto's 8-tick action space. Only then should we merge TAS examples with replay training (keeping held-out clips for real-mechanic success tests).

## Files and reports

```text
data\afk_improved\learning\
  tas_audit.json                 # raw TAS diagnostics, never used to train
  replay_cache\*.npz            # resumable per-replay caches
  native_replay_dataset.npz      # actual native observation/action samples
  dataset_manifest.json         # source SHA, stats, train/val, failures, quality filters
  anchor_logits.npy             # cached source logits for fast offline training
  replay_candidate.pt           # experimental weights (NOT promoted)
  training_report.json          # train/val CE, KL, action agreement, early stop
  verification_last.json        # cached independent test status
  reports\competition_*.json   # RocketSim result vs Nexto and original Cycle 9
  archive\                     # snapshots of intentionally replaced outputs
```

The source code is in `afk_replay_tas_learning.py`. No plugin DLL is executed. Existing licenses (especially Nexto CC BY-NC-SA 4.0) still apply. Use Rocket League/BakkesMod tools only in permitted contexts.

## Test status

The Python source compiles, safety tests and mocked replay conversion/cache tests pass, and a real CPU TorchScript training smoke test using synthetic native-shaped observations successfully updated a separate candidate without changing the source. **Real replay parsing and RocketSim match evaluation were not run here** because the current container does not have `rlgym`/`rlgym-tools` or your local `.replay` files. Run a short 10–20-replay build on Windows before a long unattended run; investigate any parser failure rather than disabling the quality checks blindly.
