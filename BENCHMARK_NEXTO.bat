@echo off
setlocal
cd /d "%~dp0"
echo This measures goals versus learned Nexto only, NOT the RLBot scripted kickoff.
if not exist ".venv\Scripts\python.exe" (
 echo Extract this add-on into your existing AI project folder.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" benchmark_vs_nexto.py --games 20 --episode-decisions 750 --seed 123
if errorlevel 1 echo ERROR: Benchmark failed; inspect traceback.
pause
