@echo off
cd /d "%~dp0"
echo EXPERIMENTAL replay defense training: 32 repeats per approved scenario, no auto-promotion.
echo Only run after fidelity and smoke tests succeed.
.venv\Scripts\python.exe -u replay_defense.py train --repeats 32 --run-name cycle9_replay_defense_v1 --save-every 4
if errorlevel 1 echo TRAIN FAILED. Send the last traceback.
pause
