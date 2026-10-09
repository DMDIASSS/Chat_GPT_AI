# Chat GPT AI — Nexto Fast Track (experimental upgrade)

**Purpose:** Give your existing Chat GPT AI project a much stronger starting policy **without deleting your current PPO checkpoints**. Uses the *real pretrained Nexto TorchScript model* as a teacher, collects Nexto-controlled RocketSim gameplay, distills to your existing 92-input/90-action/512×512 RLGym-PPO student, then evaluates it against Nexto's learned policy.

**This ZIP is an ADD-ON, not a standalone replacement**. Unzip its contents straight into your working `E:\Downloads\Chat_GPT_AI` folder, alongside `train.py` and `.venv`. In the unzip dialog, select **Extract here**, not a nested subfolder. Do **not** move/remove your `data` folder.

## Easiest path (Windows, no new API key)

1. Close the training and RLViser programs first.
2. Double-click **`INSTALL_FAST_TRACK.bat`**. Backs up original source files under `backups/`, installs the grounded preset; preserves weights, replays, and `.venv`.
3. Double-click **`RUN_FIRST_EXPERIMENT.bat`**. Runs actual environment + teacher smoke check, **5,000 1v1 decision ticks of Nexto** (up to 10,000 car examples), validates the data, then trains your own student for 12 epochs. First run may take a while; the Nexto teacher runs on your CPU to avoid competing with your laptop GPU. Saved rollouts persist in `data/datasets/nexto_rollouts/`.
4. If `data/nexto_student_policy.pt` exists, double-click **`START_STUDENT_PPO.bat`**. It **asks permission**, safely renames your older PPO checkpoint directory into a timestamped backup, then runs a fresh 1M-step PPO experiment from the distilled teacher policy. It **does not resume from the old, spinning PPO checkpoint**.
5. To measure success, double-click **`BENCHMARK_NEXTO.bat`** (no rendering) or **`WATCH_NEXTO_VS_AI.bat`** (needs RLViser). Benchmark = first to score in short simulation episodes against Nexto's **learned** policy, **not** full RLBot Nexto (scripted kickoff not replicated).
6. Only if benchmarks justify spending more training time, use `train.py` without `--fresh` or `--init-policy` to continue PPO. Track goal outcomes, touches, and human observations, not just reward.

**Alternative teacher data path:** `BUILD_NEXTO_DATA.bat` labels your GC3/SSL replay states using Nexto. The preferred path is **closed-loop Nexto rollouts**, because replays follow human controls rather than the teacher's actions. On-demand additional closed-loop data: `COLLECT_NEXTO_ROLLOUTS.bat`. Run `DISTILL_NEXTO_ROLLOUTS.bat` again after collecting. Existing shards are preserved and new ones appended.

### Exact commands (PowerShell)

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe fast_track_doctor.py --engine-smoke
.\.venv\Scripts\python.exe collect_nexto_rollouts.py --max-decisions 5000 --scenarios grounded
.\.venv\Scripts\python.exe inspect_nexto_dataset.py
.\.venv\Scripts\python.exe distill_nexto.py --dataset data\datasets\nexto_rollouts --out data\nexto_student_policy.pt --init data\bc_policy.pt --epochs 12 --batch 256
```

Distillation with `--init data\bc_policy.pt` is **optional**; omit if the file is missing or you want the student from fresh initialization. The PPO launcher verifies required files and confirms before moving any existing checkpoints.

### What this adds vs old project

- Nexto pretrained *learned* teacher model (TorchScript, ~1.8 MB)
- 90-control lookup table **verified identical** to RLGym before collecting actions
- Adapter from RLGym v2 RocketSim physics into Nexto attention observations
- Self-controlled Nexto RocketSim rollouts, including both cars, yielding soft teacher action labels
- Multiple `.npz` shards, episode-level held-out validation, KL-distillation into **compatible** DiscreteFF student weights
- Action-frequency and dataset-validity diagnostics
- Offline RocketSim student vs Nexto benchmark; optional RLViser window
- Optional **source checkout** of `RLGymPPO_CPP` for the future C++ training backend

### Compatibility fixes and verification

- **Nexto boost input scaling is corrected:** current RLGym v2 reports car boost from 0 to 100, but the original Nexto observation expects a fraction from 0 to 1. The adapter explicitly divides by 100, with a regression test.
- The included TorchScript teacher and its 90-action mapping pass unit tests here. The **real RocketSim rollout and renderer have not been executed in this container** because compatible RocketSim packages are not installed; run `FAST_TRACK_DOCTOR.bat` on your Windows PC before collecting data.
- Use this as a **teacher-student prototype**, not a finished Nexto-quality bot or finished C++ migration.

### Limitations you must know

- **No promise of beating Nexto** or performing speed flips / wavedashes / flip resets. Those need separate mechanics tasks and measurable tests.
- **Not an end-to-end compiled C++ trainer yet.** `BOOTSTRAP_CPP.bat` *clones* source only. It does not compile, automatically port our obs/rewards, or transfer checkpoints to a C++ compatible training runtime. The C++ checkpoint-conversion script works only after architecturally identical obs and actions; no C++ weights are included.
- The Nexto policy included here **does not run its external RLBot scripted kickoff**. Learned-policy benchmarks are not equivalent to official Nexto offline tournament results. This prevents inflated performance claims.
- Original Nexto builder was made for an older RLGym API; our adapter approximates its state fields. The real-RocketSim smoke test checks shapes and execution, **not game-level parity with original RLBot observations**. Test Nexto qualitatively.
- TorchScript is a deployed inference graph, not a trainable, optimizer-bearing PPO checkpoint. We distill teacher outputs into a compatible student rather than claiming direct fine-tuning.
- Windows laptop (i5-10300H, GTX 1650 Ti 4 GB, 16 GB RAM): use a small teacher collection and 2 workers first; longer multi-day training on this machine can be throttled. A cloud/high-core CPU may yield faster wall-clock results than a rewritten framework.
- Data from closed-loop rollouts are highly correlated. Train/validation groups use whole teacher episodes rather than random frames. One Nexto vs Nexto matchup doesn't cover the full game-state distribution or guarantee high-level student behavior.

## License and sources

`vendor/nexto/nexto-model.pt`, `original_agent.py`, `nexto_obs.py` and `LICENSE.txt` are from [Rolv-Arild/Necto](https://github.com/Rolv-Arild/Necto), released **CC BY-NC-SA 4.0**. This bundle retains their license and attribution and is intended for **noncommercial research** under the upstream conditions. Review those terms before publishing, redistributing, or monetizing a bot using these assets.

- [RLGym docs](https://rlgym.org/Getting%20Started/quickstart/)
- [RLGym's 90-action lookup table](https://github.com/RLGym/rlgym/blob/main/rlgym/rocket_league/action_parsers/lookup_table_action.py)
- [Nexto](https://github.com/Rolv-Arild/Necto)
- [RLGymPPO_CPP](https://github.com/ZealanL/RLGymPPO_CPP) — source checkout only, not converted training

## Troubleshooting

- **`ModuleNotFoundError: rlgym_tools`, `pyarrow`**: only the *replay* branch requires replay parser dependencies. Closed-loop rollout branch uses RocketSim + PyTorch already in your existing training environment.
- **`ModuleNotFoundError: rlviser_py`**: for the viewer only, install `rlgym[rl-rlviser]` into `.venv`.
- **`Unexpected observation shape` / `action tables differ`**: STOP. Do not train mismatched weights; send the doctor output.
- **`Checkpoint folder exists`** when starting fresh PPO: use `START_STUDENT_PPO.bat`, which backups the old checkpoint folder. Do not delete it by hand.
- **Frequent `no goal` results**: first-to-score episode time window might be too short. Increase `--episode-decisions` and collect more varied teacher situations.
- **C++ / CUDA setup problems**: see `docs/CPP_MIGRATION.md` and keep using the working Python pipeline until equivalence is proven. `BOOTSTRAP_CPP.bat` deliberately does **not** install GPU drivers or modify your Python environment.
