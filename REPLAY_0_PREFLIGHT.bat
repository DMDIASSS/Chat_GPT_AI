@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv & pause & exit /b 1)
.venv\Scripts\python.exe -m pip show rlgym-tools >nul 2>&1
if errorlevel 1 (
    echo Missing rlgym-tools dependency.
    echo Install with: .venv\Scripts\python.exe -m pip install "rlgym-tools>=2.6.0" pyarrow
    pause
    exit /b 1
)
.venv\Scripts\python.exe replay_defense.py preflight
if errorlevel 1 (echo FAILED. Send the traceback & pause & exit /b 1)
pause
