@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt (
echo Run 32_INSTALL_CUDA_RUNTIME.bat first to select your working CUDA Python.
pause
exit /b 1
)
set /p DF_CONTACT_PYTHON=<runtime_python.txt
set "DUELFORGE_DEVICE=cuda"
"%DF_CONTACT_PYTHON%" -u tools\contact_curriculum.py start --steps 5000000
if errorlevel 1 (
echo CONTACT_COMMAND_FAILED - keep output. Original potential01 and last completed checkpoints preserved.
pause
exit /b 1
)
pause
