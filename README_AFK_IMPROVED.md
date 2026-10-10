# AFK IMPROVED — Windows desktop control center v2.1 (safe upgrade)

## Installation (non-destructive)

1. Stop regular AutoLeague, the older AFK trainer, and Finishing/Tactical experiments before installing.
2. Back up `data/autoleague/champion.pt`, `data/autoleague/league_state.json`, and Cycle 9's backup file. **Do not delete the existing data folder.**
3. Extract the add-on ZIP **into your existing `E:\Downloads\Chat_GPT_AI`**. Merge files, replace the included viewer/downloader scripts when asked. Do *not* copy the ZIP to `data`.
4. For an even faster launch, `AFK_IMPROVED_PREFLIGHT.bat` checks hashes and RocketSim outside the GUI. The `data` folder is excluded intentionally. Your existing training weights are required for the preflight; they are never included in this ZIP.
5. Double-click **`AFK_IMPROVED.bat`**. If the UI does not start, run `.venv\Scripts\python.exe afk_improved_app.py` from PowerShell to see the error.
6. In the **Overview** tab choose **Validate protected files** and **Back up champion + state + Cycle 9**. Then use Training → **Check hashes**, followed by **RocketSim preflight**.
7. Training → **Start or resume**. Keep PC awake and plugged in, leave app open. Set `Hours=0` and `Cycles=0` to request indefinite cycles until manually paused; finite hours stop at a safe cycle boundary (may slightly exceed budget).
8. To stop, click **Request safe pause**; wait until the current training/evaluation cycle finishes. **Do not terminate the Python process during a save.** Start or resume uses the same experiment league and optimizer checkpoint.
9. Logs and model metadata appear in the UI and under `data/afk_improved`. Main champion/state and original Cycle 9 remain read-only; `best_verified.pt` is the best model **within the experiment** according to an independent small-episode gate. Do not manually overwrite the main champion.

## Camera as a native window

The camera tab launches a dedicated desktop window, not a browser tab. Install window support once:

`.venv\Scripts\python.exe -m pip install pywebview`

On Windows, Edge WebView2 runtime is generally required. This is a custom canvas rendering of RocketSim state: it is more muted and has a more detailed Octane-like silhouette, but it is **not an RLViser-equivalent professional 3D asset renderer**. Ball cam (`C`), car switching (`Tab`), and distance/height/angle/FOV/stiffness settings are implemented.

## Replay download

The Replays tab runs `download_ballchasing.py` with the API token in the child process environment **only**. No token is persisted. Use a local environment variable `BALLCHASING_TOKEN` if you want unattended downloads. The GUI now defaults to **ranked-duels**, documented `gc-plus` (Grand Champion or higher), and dates `2024-01-01` through `2026-10-09`. Exact GC3/SSL rank filters are **not documented** by the Ballchasing API; the app does not falsely label GC1+ results as SSL. `replay-date-after`/`replay-date-before` use RFC3339, as required by the API.

The offline replay audit reports file size, hashes and duplication only. **It does not validate full replay parse or create native Nexto action labels.** Do not enable replay imitation until exact data parsing/state-to-observation conversion and control reconstruction are independently tested.

### Should you use the whole search or Zen's replays?

For 1v1, use diverse GC3/SSL 1v1 replays from multiple strong players (ideally recent seasons). The four-playlist search contains 2v2/3v3 strategy contexts that are not transferable directly to this 1v1 learner. Specialist Zen replays may supplement analysis of recoveries, dribbles and backboard opportunities, but are too narrow alone and **not reliably supervised button inputs**.

## What the app intentionally does NOT claim

- It does not implement GigaLearn C++ training; see `AFK_IMPROVED_GIGALEARN.md`.
- It does not run 1v2 or 1v3 environments.
- It does not perform fully automatic human replay imitation.
- It does not guarantee unbounded, linear, or exponential improvement.
- RLBot v4 export exists in the existing project; v5 is not migrated.
- The experience-selection gates use short first-goal episodes, so human judgment and full-length matches remain important before replacing a main champion.

## Old files and cleanup

**Do not delete old source scripts or backups yet.** AFK Improved is an additive upgrade. Prior trainers can coexist but must not run concurrently with this one. Once the new system has operated reliably, old installer ZIPs can be archived outside the project. Avoid deleting any old `.pt`, `league_state.json`, `.training.lock` or `backups` merely because of file age.

## Support

To send results back for debugging, compress `data/afk_improved/status.json`, `data/afk_improved/runner.log`, `data/afk_improved/reports/`, and the small JSON reports. Never include your token. Do not upload models unless necessary; they can be large.

## Upgrade v2.1 — important fixes

**Windows startup:** Double-click `AFK_IMPROVED_DESKTOP.vbs` for zero persistent console window. `AFK_IMPROVED.bat` now forwards to the same invisible launcher. Internal subprocess output appears in the Logs tab and `data/afk_improved/runner.log`. If no GUI appears, inspect `data/afk_improved/gui_errors.log`.

**CUDA crash fix:** The pretrained Nexto TorchScript has a hardcoded CPU tensor in its action lookup (`ControlsPredictorDot`). On CUDA its matrix multiply throws `mat1 is on cpu, mat2 is on cuda:0`. The new AFK runner probes device safety and falls back to CPU automatically with a conspicuous message. It DOES NOT claim that a GPU-native model has been implemented. Use **CPU** for this Nexto checkpoint until a compatible re-export passes numerical parity and actual PPO tests.

**Replay search:** The download request now uses documented `replay-date-after` and `replay-date-before` RFC3339 parameters and `min-rank=grand-champion` (broad GC1+). Replays remain *data collection only*, NEVER automatically fed into the policy. Parallel downloads are capped at 3 workers and use a shared API throttle and hourly budget; resume never re-downloads a saved UUID and never skips a partially processed page. Use **Pause downloads** then **Resume/download**.

**Independent processes:** You can download replays while 1v1 training runs. The viewer runs independently in a desktop window (requires optional pywebview). Use the **Reports** tab to browse evaluations and the **Models & Backups** tab to preserve checkpoints.

**Resume after CUDA failure:** In Training, select **CPU**, then **Start or resume**. It uses the already-initialized *isolated* `data/afk_improved/league` and doesn't delete the original champion or Cycle 9. If an earlier crash left a corrupt `.partial` or incomplete checkpoint, stop and share `runner.log`; do not delete/force-restart the league blindly.

**No model files included in this patch.** Extract over the existing source directory, but back up your code first. Keep all `data` folders, checkpoints, and older CLI scripts intact. The CPU-only behavior is a safety fallback, not a speed upgrade.
