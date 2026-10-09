@echo off
setlocal
cd /d "%~dp0"
if not exist data\autoleague\champion.pt (echo ERROR: League not initialized; run AUTO_1_START first. & pause & exit /b 1)
echo Watching current ACCEPTED AutoLeague champion (not unapproved candidate).
.venv\Scripts\python.exe watch_latest_ai.py --model native --checkpoint "data\autoleague\champion.pt" --actions greedy --start grounded --speed 1
if errorlevel 1 echo Viewer error: check watch_latest_ai.py from prior viewer add-on.
pause
