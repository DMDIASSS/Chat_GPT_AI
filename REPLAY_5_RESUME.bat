@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -u replay_defense.py train --repeats 32 --run-name cycle9_replay_defense_v1 --save-every 4 --resume
if errorlevel 1 echo RESUME FAILED. Send the traceback.
pause
