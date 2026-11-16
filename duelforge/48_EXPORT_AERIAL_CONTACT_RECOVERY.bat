@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt exit /b 1
set /p DF_AIR_PYTHON=<runtime_python.txt
set "DUELFORGE_DEVICE=cuda"
set "DUELFORGE_WANDB_EXTERNAL=1"
"%DF_AIR_PYTHON%" -u tools\air_recovery.py export
if errorlevel 1 (
echo AIR_COMMAND_FAILED - original confirmed bot preserved. Keep the error above.
pause
exit /b 1
)
pause
