@echo off
cd /d "%~dp0"
if not exist runtime_python.txt (
call 0_SETUP.bat
if errorlevel 1 exit /b 1
)
set /p DF_POT_PYTHON=<runtime_python.txt
"%DF_POT_PYTHON%" -u tools\benchmark_potential_cost.py
if errorlevel 1 echo BENCHMARK_FAILED - keep the output above. Original models preserved.
pause
