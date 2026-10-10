# AFK Improved v2.1 — install on Windows

Install location: `E:\Downloads\Chat_GPT_AI` (the folder with `auto_league.py` and `.venv`).

1. Close older AFK Improved GUI, and ensure any previous trainer/download jobs are finished or safely paused. Save a copy of your **source code** folder if possible. Keep ALL model and replay folders untouched.
2. Extract the files in this ZIP directly into `E:\Downloads\Chat_GPT_AI`; agree to overwrite matching **add-on scripts**. The ZIP contains NO checkpoints, data directories, secrets, Python environments, or model weights.
3. Run `AFK_IMPROVED_PREFLIGHT.bat` and review output; it checks data hashes. To exercise the native policy forward path, run `E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe afk_improved_runner.py --check --device cuda:0` — it should explicitly say **SAFE FALLBACK to CPU** if the native JIT is incompatible.
4. Double-click `AFK_IMPROVED_DESKTOP.vbs`. This launches with `pythonw.exe` without leaving a CMD window open. `AFK_IMPROVED.bat` forwards to the same launcher.
5. In **Training**, leave device set to **CPU**, set Hours to `2` (or `0` for until paused), Cycles `0`, Steps `8192`, Evaluation games `40`, and choose **Start or resume**. Existing isolated league and candidate checkpoint will be reused; no wiping.
6. In **Replays**, choose **GC+ broad 1v1** (not verified GC3/SSL), a date range and 1–3 download workers. Click Resume/download; click Pause downloads to stop launching new jobs. Finished replay files are skipped automatically. Replay data is NOT fed to model learning.
7. Use the **Reports** tab for evaluation JSON and **Models & Backups** for secure copies. GUI errors: `data\afk_improved\gui_errors.log`; training errors: `data\afk_improved\runner.log`.

## Important restrictions

- Do not select CUDA in other older launchers such as `AUTO_1_START.bat`; the automatic safety fallback applies only to **AFK Improved** v2.1 runner. Old CUDA launchers can still crash.
- Pausing PPO finishes the **current cycle** first. Wait for `paused` status before closing. If the process crashes, already-saved rollouts are recoverable as long as their checkpoint is intact.
- Uses original `auto_league.py` unchanged. Only 1v1 PPO is implemented, not 1v2/3v3.
- The viewer needs `pywebview`, installed once using `\.venv\Scripts\python.exe -m pip install pywebview`; this is a separate desktop WebView window with simplified car models, not native Rocket League graphics.
- RLBot export currently targets v4. GigaLearn integration is a research migration, not a drop-in speed upgrade.
- The AI cannot improve exponentially forever or guarantee beating multiple Nextos.
