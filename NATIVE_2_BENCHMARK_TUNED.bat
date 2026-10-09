@echo off
cd /d "%~dp0"
echo Compare results with NATIVE_0_BENCHMARK.bat using same 20 episodes.
.venv\Scripts\python.exe native_nexto.py --mode eval --checkpoint data\native_nexto\last.pt --games 20 --eval-decisions 750 --device cpu
if errorlevel 1 (echo EVALUATION FAILED.) else (echo Benchmark complete. Compare wins and touches per 1000 decisions.)
pause
