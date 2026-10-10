# GigaLearn Research Hub v1 — honest research control center

**Status:** local Python tests pass; **requires an actual Windows C++ rebuild and GigaLearn runtime smoke test**. It is not a finished competitive Rocket League model or a verified model-merging system. This ZIP contains **NO existing model weights**, **NO proprietary RLBot assets**, **NO altered AFK files**.

## What it really does

- Dark Tkinter desktop app with readable fields: Overview / Experiments / Evolution League / Replay + TAS / AFK Bridge / Logs.
- Patches the *existing archived GigaLearn C++ example* to read research profiles from environment variables. Creates `.research_hub_original.bak` backups before changes.
- Research modes: balanced, shooting, defense, airborne control, power shot and recovery. Teamplay profiles enable GigaLearn's historical-policy self-play after versions exist; these are still its own `.lt` policies, not Nexto actors. Random or kickoff state setter. Adjustable blue/orange car counts from 1 to 3 per side. **Both teams use the newly trained GigaLearn policy; frozen Nexto adversaries are NOT integrated yet.**
- Reward shaping includes goals and directional ball movement for all modes; supplemental shots, saves, ball speed, and proximity-controlled air behavior. Does not reward raw demo counts. **These reward schemes are experiments, NOT validated against exploitability or actual game skill.**
- Creates independent, non-overwriting experiment branches, optionally seeded from a **complete GigaLearn numeric timestep directory**. It checks hashes when copying all seven model/optimizer/stat files. Never seed directly from `.pt` files.
- Safe stop request: writes `request_safe_stop.flag`, then patched C++ calls `Save()` at a PPO iteration boundary and exits. No force termination required. Requires patch **and rebuild** to work.
- Offline default: metrics/W&B sender disabled. Training logs written per experiment; checkpoint saves are independent.
- Evolution League: 6/12/24 *plans*, fixed-seed variants and CSV pairing schedules. **No fake winners; a real head-to-head benchmark between GigaLearn checkpoints must still be implemented.**
- Bridge to existing AFK scripts: legacy model comparisons, team preflight, and unchanged native Nexto/RLBot exporter; no `Cycle 9` -> `.lt` conversion.
- Replay/TAS inventory and blocked status: direct TAS and human replay imitation is NOT implemented for GigaLearn because state/action mapping and native model architecture require separate work.

## Installation on your Windows PC

**Your existing structure already contains `GigaLearn_Project/upstream/`, `build_py311/`, and the saved `4,562,496`-step C++ checkpoint. DO NOT delete those.**

1. Safely stop any running C++ PPO and AFK jobs. Back up the **entire `GigaLearn_Project` folder** (especially `build_py311/checkpoints/4562496`, `upstream/src/ExampleMain.cpp`, `upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp`).
2. Extract the ZIP to `E:\Downloads\Chat_GPT_AI` **preserving paths**. This adds `GigaLearn_Project/Research_Hub`; it does **not** overwrite your previous project scripts.
3. Open `Research_Hub/HUB_0_CHECK.bat`.
4. Run `Research_Hub/HUB_1_PATCH_CPP.bat` **once**. Source backups are created automatically. Rerunning on the already patched source makes no further edits.
5. In **x64 Native Tools Command Prompt for VS 2022**, run:
   ```bat
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub
   BUILD_IN_VS2022_DEV_PROMPT.bat
   ```
   This builds the **existing Python 3.11** `build_py311` project. It does not run training. If compilation fails, keep the log and contact us; don't delete model checkpoints.
6. Launch `Research_Hub/START_RESEARCH_HUB.vbs`. If it doesn't open, use `START_RESEARCH_HUB_DEBUG.bat` for the traceback.
7. Experiments tab: create `defense_1v2_trial_01` from **Defense Under Pressure 1v2** with NO seed for a fresh policy. For continuing your **1v1** GigaLearn model, browse the complete folder `build_py311/checkpoints/4562496` under **Optional seed checkpoint directory** before creating a *new unique **1v1** experiment name*. It cannot safely seed 1v2/3v3 due to different observation sizes; those currently start fresh.
8. Start the experiment. Open `Research_Hub/experiments/<name>/reports/training.log` to view progress. When ready, select its row and click **Request safe save + stop**. Wait until the log confirms save and the process exits. Reopening that exact experiment resumes the latest numeric checkpoint.
9. Check the `Evolution League` tab to create a **plan**, not actual contest results. Record measured outcomes before ranking.

**Resource settings:** GTX 1650 4 GB GPU: start with 12 simultaneous games, 5,000 steps per PPO iteration, 2,048 PPO minibatch, and one PPO epoch. Reduce concurrent games to 4–8 if OOM. Only one GigaLearn research process at once initially.

**Do not run `GL_4_START_CPP_TRAIN.bat` expecting to resume a Research Hub branch:** it uses the original project/launcher working directory and could start or resume a different `.lt` lineage.

## Limitations and safety

- C++ source modification and rebuilt binary not locally tested against your exact Windows checkout. The first build can reveal API variations; preserve output and send the error rather than improvising C++ changes.
- Two-sided matches in GigaLearn currently train a **shared policy**, not direct Nexto opponents, and their effectiveness needs match evaluation.
- Airborne reward uses ball altitude plus car proximity in an isolated lab. This does **not** prove actual air-dribble control, and must not be used alone to select a champion.
- Shooting reward is a proxy based on shot events and ball acceleration; it does not prove placement accuracy. A better goal mouth targeting curriculum and save prevention metric still need implementation.
- Need verified GigaLearn RLBot inference/export, multi-checkpoint competitive arena, team-role rewards, pressure state-setters, native Nexto C++ adapter, reliable TAS controller mapping and frame timing, confidence-weighted replay imitation, automated curriculum gating and model promotion before calling this a *complete* AFK replacement.
- Don't average two pretrained Nexto weight tensors or pretend a Python `.pt` is a native GigaLearn `.lt` weight.

See `docs/CURRICULUM.md` and `docs/VALIDATION_GATES.md` for the full future system sequence.
