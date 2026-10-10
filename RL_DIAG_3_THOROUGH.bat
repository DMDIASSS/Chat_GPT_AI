@echo off
cd /d "%~dp0"
echo IMPORTANT: Stop all other training/evaluation jobs first.
echo Extended 1v1 scenario evaluation: 30 paired starts per category and matchup.
echo This may take a long time. Ctrl+C stops; rerunning resumes cached completed pairs.
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: project virtualenv missing.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u rl_scenario_diagnostics.py --pairs 30 --decisions 750
if errorlevel 1 echo Benchmark failed; completed pairs remain in cache for resume.
pause
