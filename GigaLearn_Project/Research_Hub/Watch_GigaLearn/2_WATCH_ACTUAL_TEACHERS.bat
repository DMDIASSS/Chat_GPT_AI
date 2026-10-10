@echo off
setlocal
cd /d "%~dp0..\..\.."
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY%" (echo ERROR: Python 3.11 missing & pause & exit /b 1)
if not exist "GigaLearn_Project\build_py311\Release\GigaLearnWatchTeacher.exe" (echo ERROR: Run the teacher build first & pause & exit /b 2)
"%PY%" -u "GigaLearn_Project\Research_Hub\Watch_GigaLearn\watch_teacher_gui.py"
if errorlevel 1 pause
