@echo off
setlocal
cd /d "%~dp0"
set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY311%" (
  "%PY311%" ADD_EXPERIMENT_MANAGEMENT.py
) else (
  py -3.11 ADD_EXPERIMENT_MANAGEMENT.py
)
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Patch failed. Your experiments and checkpoints were not changed.
pause
exit /b %RESULT%
