@echo off
cd /d "%~dp0"
echo IMPORTANT: Pause or stop AFK and AutoLeague before running this benchmark.
echo Scenario test: 8 paired starts per scenario / matchup. First-goal episodes only.
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: project virtualenv missing.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u rl_scenario_diagnostics.py --pairs 8 --decisions 750
if errorlevel 1 echo Benchmark failed; completed pairs remain in cache for resume.
pause
