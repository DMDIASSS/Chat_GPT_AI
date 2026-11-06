@echo off
setlocal
cd /d "%~dp0"
echo Native Chronos Breakout and Galactus Octane. Close other trainers. Runs until paused or guarded.
set "GIGA_PY=.venv_native\Scripts\python.exe"
if not exist "%GIGA_PY%" set "GIGA_PY=..\novaforge\.venv\Scripts\python.exe"
if not exist "%GIGA_PY%" goto missing
"%GIGA_PY%" -u run.py train
if errorlevel 1 goto failed
pause
exit /b 0
:missing
echo Python environment missing. Install NovaForge Python 3.11 first.
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. No older project was reset.
pause
exit /b 1
