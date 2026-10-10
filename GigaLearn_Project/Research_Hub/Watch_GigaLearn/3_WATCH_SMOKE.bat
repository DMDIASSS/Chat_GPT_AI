@echo off
setlocal
cd /d "%~dp0..\..\.."
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo ERROR: Python 3.11 missing & pause & exit /b 1)
"%PY%" -u "GigaLearn_Project\Research_Hub\Watch_GigaLearn\watch_core.py" --list
if errorlevel 1 (echo ERROR: model scan failed & pause & exit /b 2)
echo Model scan complete. If models are listed, start 2_WATCH.bat.
pause
