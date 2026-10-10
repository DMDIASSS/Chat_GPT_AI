@echo off
cd /d "%~dp0"
echo EXPERIMENTAL, only a single pass per approved replay drill.
.venv\Scripts\python.exe -u replay_defense.py train --repeats 1 --run-name cycle9_replay_smoke --save-every 1
if errorlevel 1 echo TRAIN FAILED. Send traceback and do not scale up.
pause
