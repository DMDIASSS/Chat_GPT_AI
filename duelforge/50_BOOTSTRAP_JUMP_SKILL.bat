@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt exit /b 1
set /p DF_JUMP_PYTHON=<runtime_python.txt
set "DUELFORGE_DEVICE=cuda"
start "Jump bootstrap W&B uploader" "%DF_JUMP_PYTHON%" -u tools\wandb_sidecar.py --root runs\jump01
"%DF_JUMP_PYTHON%" -u tools\jump_bootstrap.py start --updates 300
if errorlevel 1 (
echo JUMP_BOOTSTRAP_FAILED - confirmed model and last completed checkpoint preserved.
pause
exit /b 1
)
