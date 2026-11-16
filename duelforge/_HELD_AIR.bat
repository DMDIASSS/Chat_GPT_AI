@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo RUNTIME_MISSING - run your existing CUDA setup first. Models were preserved.
exit /b 1
)
set /p DF_HELD_PYTHON=<runtime_python.txt
"%DF_HELD_PYTHON%" -u tools\held_air.py %*
if errorlevel 1 (
echo STATIONARY_AIR_COMMAND_FAILED - keep this output. Existing runs were preserved.
exit /b 1
)
