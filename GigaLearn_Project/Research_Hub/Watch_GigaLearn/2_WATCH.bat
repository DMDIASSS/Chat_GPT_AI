@echo off
setlocal
cd /d "%~dp0..\..\.."
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo ERROR: Python 3.11 not found at %PY% & pause & exit /b 1)
"%PY%" -u "GigaLearn_Project\Research_Hub\Watch_GigaLearn\watch_gui.py"
if errorlevel 1 pause
