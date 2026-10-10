@echo off
cd /d "%~dp0"
echo Isolated 96-decision PPO smoke test. Does NOT touch main champion.
".venv\Scripts\python.exe" -u finishing_train.py --mode smoke
if errorlevel 1 echo FAILED: send me the full error before running the long trainer.
pause
