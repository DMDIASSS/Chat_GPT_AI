@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch numpy
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install lz4 zstandard
if errorlevel 1 goto failed
if not exist "tools" mkdir tools
echo.
echo Python setup complete. CPU is appropriate for this small model.
echo Download luau-windows.zip from https://github.com/luau-lang/luau/releases/latest
echo Put luau.exe and luau-compile.exe inside this folder's tools directory.
echo Then run PREPARE_TRAINING.bat with your quoted RoWorld place path.
echo For CUDA, replace the CPU torch installation using https://pytorch.org/get-started/locally/
exit /b 0
:failed
echo Setup failed; read the error above. Python 3.10 or newer is required.
exit /b 1
