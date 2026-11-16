@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo Select your existing runtime first.
pause
exit /b 1
)
set /p DF_AIR_LOG_PYTHON=<runtime_python.txt
"%DF_AIR_LOG_PYTHON%" -u tools\wandb_sidecar.py --root runs\air01
if errorlevel 1 pause
