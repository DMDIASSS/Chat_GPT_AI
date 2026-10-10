@echo off
setlocal
cd /d "%~dp0..\..\.."
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo ERROR: Python 3.11 not found & pause & exit /b 1)
"%PY%" "GigaLearn_Project\Research_Hub\Watch_GigaLearn\install_teacher_watch.py"
if errorlevel 1 (echo Installation failed - no training checkpoint changed & pause & exit /b 2)
pause
