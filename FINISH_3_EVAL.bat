@echo off
cd /d "%~dp0"
echo Comparing isolated PPO candidate against frozen Cycle 9 and Nexto.
".venv\Scripts\python.exe" -u finishing_train.py --mode eval --eval-games 60 --eval-decisions 600
if errorlevel 1 echo Evaluation failed; main champion remains unchanged.
pause
