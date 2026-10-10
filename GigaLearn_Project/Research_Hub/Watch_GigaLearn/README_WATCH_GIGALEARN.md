# Watch real GigaLearn .lt models with RocketSim — v1

**What it does:** This is an inference-only, separate GigaLearn C++ 1v1 watch executable (`GigaLearnWatch.exe`) + Python viewer bridge. It drives RocketSim with the actual `.lt` actor models using the same AdvancedObs and DefaultAction network config as the working Gameplay Evaluator. It streams the resulting native RocketSim states into your existing **RLViser** renderer, with an optional ZealanL **RocketSimVis** UDP output mode. This does **not** use the old 92-observation/Nexto `.pt` Python watch script. It never trains or writes to model checkpoints.

## Install

1. Safely stop any existing GigaLearn training or evaluation. Back up `Research_Hub/experiments` and `upstream/CMakeLists.txt` if you want an extra manual rollback copy.
2. Extract this ZIP **into `E:\Downloads\Chat_GPT_AI`** preserving folders.
3. Double-click `GigaLearn_Project\Research_Hub\Watch_GigaLearn\0_INSTALL.bat`. It adds exactly one new separate CMake target and a new source file, and makes a backup of CMake. It refuses conflicting pre-existing files.
4. Open **x64 Native Tools Command Prompt for VS 2022**. In it:

   ```bat
   cd /d E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Watch_GigaLearn
   1_BUILD.bat
   ```

5. Once SUCCESS appears, double-click `3_WATCH_SMOKE.bat`. You should see the discovered 1v1 models. Then double-click `2_WATCH.bat` and select the two models you want. Recommended first match: `replay_foundation_01` vs `smoke_balanced_01`.
6. Keep **Viewer = rlviser**, speed 1.0, greedy actions. Click **Watch in RocketSim**.

Your original project already had an RLViser viewer. This package deliberately does **not** reinstall it or download incompatible DLLs. A working `rlviser.exe` should be in `E:\Downloads\Chat_GPT_AI`. If the old viewer still works but this reports a missing `RocketSim` or `rlviser_py` dependency, send the error; the Python interpreter/site-packages need adjustment rather than a new viewer implementation.

## Camera

RLViser menu initially blocks keys. Press `Esc` to close it. `1` or `2` follows a car, `9` director camera, `0` free camera and `W/A/S/D` move the free camera; `Space` up, `Left Ctrl` down. You can set 0.5x playback and sampled actions in the GUI. Look at whether the bot actually drives to the ball and makes touches instead of relying on all-draw tournament scores.

The optional `rocketsimvis` mode sends JSON to `127.0.0.1:9273`. You must separately install and launch https://github.com/ZealanL/RocketSimVis first. It is a different viewer, so don't select it unless you have that viewer running.

## Technical limits

- **1v1 only** in v1; GigaLearn observations change with team sizes.
- The same kickoff seed is used for each two-episode pair, with model A playing both Blue and Orange across the pair. After a goal or the time cap, the next episode starts automatically. There is no Rocket League game client.
- Inference can be slow on CPU; GPU mode is optional but more brittle on your GTX 1650.
- RLViser displays ~15 physics states per second and interpolates between them; native RocketSim runs 120 physics ticks/second with 8 ticks per action. This is **visualization of real GigaLearn-controlled RocketSim states**, not a separate imitation simulation.
- Direct RLViser Python binding and MSVC build have **not been tested here on your Windows installation**. This ZIP is source-checked and Python-tested, not a guaranteed Windows binary.
- No C++ simulator code is modified, no saved checkpoint is overwritten, and no `.pt`/`.lt` conversion is done. If the build fails, your existing Hub trainer and previous viewer still work.

### CLI (optional)

```bat
cd /d E:\Downloads\Chat_GPT_AI
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -u "GigaLearn_Project\Research_Hub\Watch_GigaLearn\watch_core.py" --list
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -u "GigaLearn_Project\Research_Hub\Watch_GigaLearn\watch_core.py" --a replay_foundation_01 --b smoke_balanced_01 --speed 0.5
```

Ctrl+C to stop the CLI. You can set `--sample` to use stochastic policy actions or `--gpu` for CUDA inference.

### Troubleshooting

- **`GigaLearnWatch.exe not built`:** run `1_BUILD.bat` from the VS 2022 x64 developer prompt, and copy the first actual compiler error.
- **`No module named RocketSim` / `rlviser_py`:** verify the old `.venv` viewer works; do not reinstall CUDA or delete venv.
- **Black screen:** verify `rlviser.exe` in `E:\Downloads\Chat_GPT_AI`, press `Esc` and `1` or `2`, and check the logs for `[WATCH ERROR]`.
- **Models missing:** check `Research_Hub\experiments\<name>\experiment.json` says teams Blue 1/Orange 1 and numbered checkpoint has `POLICY.lt`, `SHARED_HEAD.lt`.
- **No movement / only draws:** may be genuine weakness. Try **sample** mode and compare against the same starting seed. Do not treat views or touch counts as proof of competitive skill.
