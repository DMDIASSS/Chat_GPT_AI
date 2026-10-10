@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY%" goto run
where py >nul 2>&1
if errorlevel 1 (
 echo ERROR: Python 3.11 not found. Set PATH or install Python 3.11.
 pause
 exit /b 1
)
set "PY=py"
:run
if /i "%PY%"=="py" (
 py -3.11 -u "%~dp0watch_teacher_kickoff_probe.py" --teacher %1 --viewer headless --decisions 120 --episodes 2
) else (
 "%PY%" -u "%~dp0watch_teacher_kickoff_probe.py" --teacher %1 --viewer headless --decisions 120 --episodes 2
)
if errorlevel 1 echo DIAGNOSTIC FAILED: see error above.
pause
