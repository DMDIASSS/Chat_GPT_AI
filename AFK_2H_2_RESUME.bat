@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo ERROR: Missing project .venv & pause & exit /b 1)
echo Resuming latest PAUSED or INTERRUPTED AFK run.
echo Previous preliminary benchmark will be reused. Training time budget: 120 NEW minutes.
echo STOP other AutoLeague training jobs first; no admin rights needed.
".venv\Scripts\python.exe" -u afk_two_hour.py --resume-latest --minutes 120
if errorlevel 1 echo Run failed or was interrupted. Check STATUS.json and AFK_LOG.txt.
pause
