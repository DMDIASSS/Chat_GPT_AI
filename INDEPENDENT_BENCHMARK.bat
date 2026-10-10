@echo off
setlocal
cd /d "%~dp0"
echo Independent READ-ONLY Nexto benchmark: 200 first-goal episodes.
echo Does NOT train, promote, overwrite checkpoints or change AutoLeague state.
if not exist ".venv\Scripts\python.exe" (echo ERROR: missing project .venv & pause & exit /b 1)
".venv\Scripts\python.exe" -u independent_nexto_benchmark.py --pairs 100 --baseline-pairs 20 --decisions 750
if errorlevel 1 (echo BENCHMARK FAILED. Send the error. & pause & exit /b 1)
echo Upload the new benchmark_reports\heldout_nexto_*.json file to ChatGPT.
pause
