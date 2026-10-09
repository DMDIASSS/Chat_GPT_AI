# SkillForge — Watch the real physics attempts

**No model training or checkpoint changes.** These files are an addon to your existing SkillForge v1. Extract the ZIP directly to `E:\Downloads\Chat_GPT_AI`, alongside `skillforge_search.py` and `skillforge_core.py`.

### Open a visual replay

1. Double-click **`SF_WATCH_BEST_ATTEMPT.bat`**. This loads your existing `data\skillforge\wavedash\discovery.json` and loops the best attempt, half speed, in RLViser.
2. Inside **RLViser**, press **Esc** to close its default menu and press **1** or **2** to focus the moving car (depending on which team/car got the scenario). A director / ball camera can miss the test car: the ball is deliberately kept far away.
3. Observe: *jump/dodge timing*, whether the car hits the ground **during** a dodge, whether it tumbles a full rotation, and whether it leaves the landing stable with extra speed.
4. The terminal reports exactly when the dodge and landing occur, why verification failed, and speed gain. It also saves 120Hz traces in `data\skillforge\wavedash\viewer_traces\`.

Optional: **`SF_WATCH_SEARCH_EVOLUTION.bat`** replays the best candidate of each generation of the completed CEM search in order so you can see what was tried. **`SF_WATCH_DODGE_CONTROL.bat`** shows a normal airborne flip for comparison; a normal flip is expected to *fail* the wavedash detector.

### Extra options

Open PowerShell in the project directory:

```powershell
.\.venv\Scripts\python.exe skillforge_watch.py --mode best --speed 0.25 --repeat 10
.\.venv\Scripts\python.exe skillforge_watch.py --mode progress --speed 1 --repeat 1
.\.venv\Scripts\python.exe skillforge_watch.py --mode generation --generation 3 --seed 100100101
.\.venv\Scripts\python.exe skillforge_watch.py --mode idle --repeat 2
```

The viewer re-simulates saved controller parameters using the same `Simulator` and `macro_control` as training; it's not a video recording. RocketSim's real preflight already worked for you, but the new RLViser replay integration still needs to be checked on Windows.

**Important:** `0/16` success means the current search found **no verified wavedash**. Viewer shows the best *failed attempt*, not a trained bot. The 10K Nexto / kickoff checkpoints are not touched.

RLViser camera controls: https://github.com/VirxEC/rlviser
