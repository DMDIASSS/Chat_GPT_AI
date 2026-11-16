@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt exit /b 1
set /p DF_JUMP_PYTHON=<runtime_python.txt
set "DUELFORGE_DEVICE=cuda"
"%DF_JUMP_PYTHON%" -u tools\jump_bootstrap.py watch
if errorlevel 1 (
echo JUMP_BOOTSTRAP_FAILED - confirmed model and last completed checkpoint preserved.
pause
exit /b 1
)
pause
