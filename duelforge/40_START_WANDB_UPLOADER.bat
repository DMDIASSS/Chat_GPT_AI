@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt exit /b 1
set /p DF_UPLOADER_PYTHON=<runtime_python.txt
"%DF_UPLOADER_PYTHON%" -u tools\wandb_sidecar.py --root runs\contact01
