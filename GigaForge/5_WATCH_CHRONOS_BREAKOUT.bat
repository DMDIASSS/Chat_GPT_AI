@echo off
setlocal
cd /d "%~dp0"
echo Blue is Chronos on Breakout. Orange is original Galactus on Octane. Pause training before viewing.
set "GIGA_PY=.venv_native\Scripts\python.exe"
if not exist "%GIGA_PY%" set "GIGA_PY=..\novaforge\.venv\Scripts\python.exe"
if not exist "%GIGA_PY%" goto missing
"%GIGA_PY%" -u run.py watch --family chronos
if errorlevel 1 goto failed
pause
exit /b 0
:missing
echo Python environment missing. Install NovaForge Python 3.11 first.
:failed
echo NATIVE_COMMAND_FAILED - keep the error above. No older project was reset.
pause
exit /b 1
