# Chat GPT AI — Mechanics Lab v0.1 (native Nexto)

**Goal:** experiment with recovery, kickoff efficiency, wavedashes, aerial contacts, dribble control, flip-reset acquisition, double taps and pinch *proxies*, WITHOUT losing your proven `best_10k.pt` baseline.

This is a **specialist fine-tuning / benchmarking add-on**, not an already-trained mechanical bot. It does not magically turn an RL agent into a reliable freestyler. The first four tasks are foundations; the later tasks are **experimental hard tasks** and likely need expert demonstrations and many more decisions. There is no automatic skill-merging system yet. Each stage is an **independent branch** initialized from the saved 10K model. To retain competitive skills, only combine improvements after paired evaluation against frozen Nexto.

## Install

1. **Keep** `E:\Downloads\Chat_GPT_AI\data\native_nexto\best_10k.pt` and `last.pt` backed up. Do not delete them.
2. Extract ZIP **into** `E:\Downloads\Chat_GPT_AI` next to `native_nexto.py`, `nexto_teacher.py` and `train.py`. These files are not replaced.
3. Confirm `vendor\nexto\nexto-model.pt` and the already-working `.venv` are present.
4. Run `MECH_0_VALIDATE.bat`, then **`MECH_0_REAL_SIM_TEST.bat`**. The second script checks **one real RocketSim step** per task on your Windows installation. If it fails, send the **first traceback** before training anything.

## First experiment (safe)

Run `MECH_1_RECOVERY_SMOKE.bat` (1,024 native decisions), then `MECH_2_EVALUATE_RECOVERY.bat`.

The first run writes **only**:

`data\mechanics\recovery\last.pt` and timestamped step snapshots.

The evaluator prints success counts on **identical seeded starts** for baseline vs candidate, and a separate Nexto first-to-score sanity check. It stores JSON under `data\mechanics\recovery\evaluations\`. **It never alters weights**. It is normal for 1,024 decisions not to produce any skill gains.

To *watch* recovery training tasks in RLViser, run `MECH_WATCH_STAGE.bat`, choose `recovery` and `candidate` or `baseline`. This is a drill visualization, not a competitive self-play match. You can also use your existing viewer for standard matches, specifying the candidate:

```powershell
.\.venv\Scripts\python.exe watch_latest_ai.py --model native --checkpoint "data\mechanics\recovery\last.pt" --actions greedy --start kickoff
```

The custom `--checkpoint` is essential: `WATCH_LATEST_AI.bat` will NOT auto-select these specialist files.

## More stages

| Stage | Setup | Success *proxy* (not a claim of real-game mastery) |
|---|---|---|
| `recovery` | Midair tilted car descending | 3 stable decisions wheels-down and moving |
| `wavedash` | Low car falling with a dodge | Low-altitude flip followed by faster controlled landing |
| `kickoff` | Normal kickoff vs Nexto | First touch within ~2.5 s; **not proof of a speedflip** |
| `aerial_touch` | Ball high in air, car on approach | Touch above minimum altitude |
| `air_dribble` | Car and ball moving together airborne | Sustained proximity, speed match and a touch |
| `flip_reset` | Aerial car with dodge spent, near ball | Regain flip while still airborne |
| `double_tap` | Backboard approach | Own touch, backboard bounce, second touch and goal |
| `ground_pinch` | Ball on floor and closing car | Hard ball acceleration away from floor toward attack |
| `wall_pinch` | Ball near sidewall | Hard ball acceleration away from wall toward attack |
| `ceiling_touch` | High car near ceiling and high ball | Airborne touch after ceiling-area setup; **not a ceiling shot** |

To train any stage explicitly (for example, aerial contact):

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe mechanics_train.py --stage aerial_touch --steps 1024 --rollout 256 --minibatch 64 --epochs 2 --episode-decisions 120 --device cpu
```

To extend *that same* stage to 10,240 **cumulative** decisions:

```powershell
.\.venv\Scripts\python.exe mechanics_train.py --stage aerial_touch --resume --steps 10240 --rollout 256 --minibatch 64 --epochs 2 --episode-decisions 120 --device cpu
```

Run evaluation afterward:

```powershell
.\.venv\Scripts\python.exe mechanics_evaluate.py --stage aerial_touch --episodes 20 --seed 741 --competitive --competitive-games 20
```

For kickoff training add `--opponent nexto` to BOTH training and mechanics evaluation. Comparing `kickoff` training against passive opponent is too easy. For hard advanced stages, the small initial 1,024-decision run is **only a pipeline smoke test**.

## What is safe, and what isn't

- ✅ `best_10k.pt` stays untouched and is the KL anchor reference for every task.
- ✅ The original `vendor\nexto\nexto-model.pt` stays untouched (upstream **CC BY-NC-SA 4.0**; keep license / attribution).
- ✅ Each stage has a separate candidate file. No automatic replacement of any competitive policy.
- ✅ Trainer refuses to overwrite existing stage checkpoint without explicit `--resume`.
- ✅ Use the evaluator to look for **success rate** and loss of first-to-goal performance, not just more touches.
- ⚠️ Some custom resets are challenging to make physically perfect; real RocketSim preflight is required.
- ⚠️ 12–20 kickoff/first-to-score episodes with repeated setups do not establish superiority. Use varied side-balanced seeds and eventually real full matches.
- ⚠️ Our native Nexto actor has 90 discrete actions at 8 physics ticks/action. Some fine mechanics may need finer action timing / a richer action space, plus recorded expert mechanic demonstrations.
- ⚠️ PPO against a frozen Nexto anchor can still **forget** previous skills. Don't promote a specialized actor without evaluation.
- ⚠️ This v0.1 uses one RocketSim engine in Python for correctness and GPU-safe training. It is **not yet a C++ multi-environment high-speed trainer**. C++/GigaLearn migration is a separate task.

## Next milestones (not included in v0.1)

1. Validate each start in RLViser against actual RocketSim and adjust infeasible resets.
2. Add expert action traces for speedflips/wavedashes and genuine flip resets; a 15 Hz action policy may require action-repeat changes.
3. Train specialized policies to a measurable success rate (e.g., 80% successful, varied held-out starts), with real mechanic checks.
4. Mix specialist scenarios with competitive 1v1 in a **single** policy and regularize against `best_10k.pt`. Independently trained stage weights cannot simply be averaged safely.
5. Promote only after a large, side-balanced baseline win-rate test versus original Nexto and multiple other opponents, plus recovery/skill benchmarks.

**Offline games and RocketSim only; not for online ranked matchmaking.**

## One-click task menu

If you prefer not to paste PowerShell commands, use **`MECH_LAB_MENU.bat`** after the preflight. Pick a numbered skill to run a 1,024-decision **smoke training**, or press `C` to evaluate it and `D` to watch it. The menu never auto-promotes specialist policies. To grow a stage beyond 1,024 decisions, use the explicit `--resume` command above.
