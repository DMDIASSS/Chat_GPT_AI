# Chat GPT AI — AutoLeague v1 (native Nexto; guarded self-play)

**Purpose:** automate experiment → independent evaluation → accept or rollback. No mechanics shortcuts, no guaranteed improvement. Use only simulated/offline Rocket League matches.

## Installation

Extract this ZIP directly into `E:\Downloads\Chat_GPT_AI` so `auto_league.py` is beside your existing `native_nexto.py`, `nexto_teacher.py`, `watch_latest_ai.py`, `vendor/nexto/nexto-model.pt`, `.venv`, `chatgpt_ai/`, and `data/` folders. The ZIP has **no pretrained weights**. Previous training is preserved. Keep your saved `data/native_nexto/best_10k.pt` and `data/mechanics/kickoff/last.pt`.

1. Double-click **`AUTO_0_PREFLIGHT.bat`**. This loads your real checkpoint and takes one RocketSim physics step. Stop if it fails.
2. Try **`AUTO_2_ONE_SMALL_CYCLE.bat`** first to confirm real training → evaluation → backup → rollback/promotion works on Windows. It is only a functional smoke test, not a meaningful improvement trial, and **--no-promote** ensures it cannot replace the champion.
3. Run **`AUTO_1_START.bat`** for continuous training from `best_10k.pt`. **Ctrl+C** stops at the current operation; resume by running again. Champion is always saved separately from untested candidates.
4. Or run **`AUTO_1_START_FROM_KICKOFF.bat`** to train a *separate league* starting from the saved kickoff-model checkpoint; that league uses `data/autoleague_kickoff/`, not the regular `data/autoleague/`.
5. **`AUTO_WATCH_CHAMPION.bat`** watches the last *accepted* champion playing itself in RLViser; **`AUTO_VIEW_STATUS.bat`** lists checkpoints, verdicts, and backups.

### What actually happens

- Train a real TorchScript **Nexto attention actor**, 1v1, through native RLGym/RocketSim PPO. The rival is 55% a frozen snapshot of the *currently training model* (**self-play**), 25% the accepted champion (historical self-play), 20% unmodified frozen Nexto. Rival is deterministic/greedy; learner samples for exploration. That split is experimental, not proven optimal.
- Training resets: **75% grounded randomized plays, 25% kickoffs** (not the identical kickoff loop). PPO has small policy updates, a separate value network, and a KL anchor to the last champion. Basic reward is goal/progress/proximity shaping **without flat ball-touch rewards**. These are still experimental hyperparameters.
- Candidate segment: by default **8,192 decisions**; candidate saved after each 512-decision rollout; longer-term progress remains in separate `candidate.pt`. `Ctrl+C` may lose up to one incomplete rollout.
- Independent evaluation every segment: **40 scenario seeds**, alternating orange/blue; 75% randomized ground plays + 25% kickoffs, with **candidate vs original Nexto**, **champion vs original Nexto** on the *same seeded starting states*, and **candidate directly vs champion**. `W/L/D`, comparison score `(wins + draws/2)/games`, number of unique initial states, and reports are stored. These are **first-goal episodes, not full five-minute matches**. Unusually many identical starts block promotion.
- **PROMOTE:** candidate must score at least four percentage points above champion against Nexto AND do at least 55% head-to-head with more wins than losses. A tentative heuristic, not statistical proof of superiority. Only then atomically replace `data/autoleague/champion.pt` (source checkpoints never overwritten).
- **REJECT:** substantial decline (more than 10 points worse vs Nexto or less than 45% direct head-to-head); reject checkpoint is archived and SHA256-blacklisted. Subsequent cycles reduce actor learning rate after repeated failures. **INCONCLUSIVE:** not proven stronger; save as inconclusive and revert to champion, but not blacklist. Original champion is never harmed by these decisions.
- **Backups:** every **5 wall-clock minutes, checked at the next completed rollout**, timestamped `..._champion.pt` and `..._candidate.pt` under `data/autoleague/backups/`, plus an initial backup and forced backup before every evaluation/promotion. All backups are retained. Monitor disk space.
- A `league_state.json` contains the champion's SHA256. A missing or altered champion stops training. If the machine shuts off during a promotion, a two-phase journal lets the manager finish that exact pending promotion safely on restart.

### What about automatic replays?

The included `download_ballchasing.py` downloads **public** ranked 1v1 `.replay` files using the Ballchasing API, with the local hourly rate budget. To enable it set the API token in the **same PowerShell session** and launch the Python manager there:

```powershell
cd E:\Downloads\Chat_GPT_AI
$env:BALLCHASING_TOKEN = "paste_your_own_token_here"
.\.venv\Scripts\python.exe -u auto_league.py --source data\native_nexto\best_10k.pt
```

The downloader runs every 60 min (initial run immediately) **in a daemon thread**; max 3 new replays per poll. Replays and analysis live under `data/autoleague/replays`, `replay_analysis_index.json`, and `replay_analysis_summary.json`. The parser uses `rlgym_tools` if available. It analyzes human replay ball height, speed, sampled touches and other descriptive physics. Replay API failures **never stop training**. If token is missing, replay downloads are **off**, not silently fabricated. If you prefer, `AUTO_REPLAYS_DOWNLOAD_ONCE.bat` tests downloading separately in that same authenticated terminal session.

**Critical honesty:** downloaded human replays are NOT automatically used as PPO training examples in v1. Reconstructed replay controller labels do not directly match the frozen Nexto actor's observations and action interface. Blindly adding them could wreck your good model. After we verify this stable training system, we can add a properly validated *off-policy replay imitation* stage.

### What about 1v2 and 1v3 Nextos?

Not implemented yet. Our current `nexto_teacher.encode_v2_state()` **requires exactly two cars**, and the model consumes a fixed 37-entity observation. Increasing player count without redesigning/masking the representation produces invalid inputs. This v1 always uses genuine 1v1, even if it wins all its games. For challenging evaluations now, use extra randomized seeds and the historical champion pool. Multi-car handicap matches are a separate compatibility project; no deceptive `1v3` flag.

### Files and recoverability

- `data/autoleague/champion.pt` — accepted, safe champion (watch this)
- `data/autoleague/candidate.pt` — unapproved current training experiment (resumable)
- `data/autoleague/backups/` — timestamped champion + candidate backups
- `data/autoleague/rejected/` — archived bad candidates
- `data/autoleague/inconclusive/` — archived ambiguous candidates
- `data/autoleague/blacklist.json` — rejected checkpoint hashes and reasons
- `data/autoleague/reports/`, `history.jsonl` — every evaluation verdict
- `data/autoleague/league_state.json` — SHA256-verified active champion / pending promotion

To watch any backup, use:

```powershell
.\.venv\Scripts\python.exe watch_latest_ai.py --model native --checkpoint "data\autoleague\backups\EXACT_FILENAME.pt" --actions greedy --start grounded --speed 1
```

If the original checkpoint is missing, do not start training until it is restored. **Do not delete the `league_state.json` to reset** an existing league; it protects your lineage and recovery.

### Known limitations

- This is a tested Python implementation, **not a proven autonomous SSL bot**. End-to-end RocketSim preflight and a real training cycle still need to pass on your Windows installation.
- PPO reward is still heuristic, and performance on a different opponent can regress even when the gate passes. Testing against other bots and full 5-min games is the next evaluation upgrade.
- Multiple parallel league processes writing the same `data/autoleague/` are not safe; run ONE trainer per league at a time.
- It cannot download replays unless you supply a Ballchasing token; it cannot access actual Rocket League ranked servers.
- Nexto weights and derivative models are **CC BY-NC-SA 4.0**. Keep the original license and attribution; do not use this derived bot commercially without clearing rights.
