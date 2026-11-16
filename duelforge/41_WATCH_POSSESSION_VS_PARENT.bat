@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo CUDA Python selection missing; run 32_INSTALL_CUDA_RUNTIME.bat first.
pause
exit /b 1
)
set /p DF_STAGE_PYTHON=<runtime_python.txt
"%DF_STAGE_PYTHON%" -u tools\contact_curriculum.py watch --stage possession --seconds 120
if errorlevel 1 (
echo STAGE_COMMAND_FAILED - checkpoint preserved. Keep the output above.
pause
exit /b 1
)
pause
