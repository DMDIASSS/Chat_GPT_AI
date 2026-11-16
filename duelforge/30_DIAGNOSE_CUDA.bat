@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
py -3.11 tools\setup_project.py
if errorlevel 1 goto failed
)
set /p DF_CUDA_PYTHON=<runtime_python.txt
"%DF_CUDA_PYTHON%" -u tools\diagnose_cuda.py
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo CUDA_DIAGNOSTIC_FAILED - keep the output above. No training started.
pause
exit /b 1
