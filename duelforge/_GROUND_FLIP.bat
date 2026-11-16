@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo RUNTIME_MISSING - use your existing CUDA setup first. Models preserved.
exit /b 1
)
set /p DF_FLIP_PYTHON=<runtime_python.txt
"%DF_FLIP_PYTHON%" -u tools\ground_flip.py %*
if errorlevel 1 (
echo GROUND_FLIP_COMMAND_FAILED - keep this output. Original runs preserved.
exit /b 1
)
