@echo off
cd /d "%~dp0"
echo STOP training and AutoLeague before using. This may take a long time.
if not exist ".venv\Scripts\python.exe" (echo Missing .venv Python & pause & exit /b 1)
".venv\Scripts\python.exe" -u round_robin_evaluator.py --games-per-pair 50 --seconds 180 --all-scripted-kickoffs
if errorlevel 1 echo Run this again to resume completed games.
pause
