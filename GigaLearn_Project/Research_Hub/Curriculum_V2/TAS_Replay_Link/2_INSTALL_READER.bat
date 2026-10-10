@echo off
setlocal
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo Python 3.11 missing & pause & exit /b 1)
"%PY%" "%~dp0install_reader.py"
if errorlevel 1 (echo FAILED; CPP left unchanged & pause & exit /b 1)
echo PATCHED: must rebuild before training. Run 3_BUILD_REPLAY_BC.bat in VS x64 Native Tools Command Prompt.
pause
