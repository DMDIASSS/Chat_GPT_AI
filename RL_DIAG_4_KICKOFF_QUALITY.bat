@echo off
cd /d "%~dp0"
echo KICKOFF QUALITY benchmark: 40 matched start pairs per matchup, 6 simulated seconds.
echo Safely pause all AFK/AutoLeague trainers first. This does NOT train or alter weights.
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Project Python venv missing.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u rl_scenario_diagnostics.py --kickoff-only --pairs 40 --decisions 90 --control-pairs 10
if errorlevel 1 echo Error: see traceback above. All completed pairs are cached.
pause
