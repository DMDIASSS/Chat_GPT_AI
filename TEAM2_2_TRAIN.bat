@echo off
cd /d "%~dp0"
echo Experimental 2v2 shared-policy PPO vs two frozen Nextos and two frozen Cycle9s.
echo Do NOT run if AFK or AutoLeague 1v1 is active.
".venv\Scripts\python.exe" -u teamplay_v2.py train --samples 16384 --rollout 128 --episodes 330 --run-dir data\teamplay_v2\cycle9_shared_2v2
if errorlevel 1 echo TRAINING FAILED. Send the last traceback.
pause
