@echo off
setlocal
cd /d "%~dp0"
py -3.11 -u tools\install_cuda_runtime.py
if errorlevel 1 (
echo CUDA_INSTALL_FAILED - keep the output above and cuda_install_status.json. Existing models and NovaForge environment were preserved.
pause
exit /b 1
)
pause
