@echo off
setlocal
cd /d "%~dp0"
echo READ-ONLY GigaLearn student movement audit: no weights or trainer edits.
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY%" goto run
where py >nul 2>&1
if errorlevel 1 (
 echo ERROR: Python 3.11 not found.
 pause
 exit /b 1
)
set "PY=py"
:run
if /i "%PY%"=="py" (
 py -3.11 -u "%~dp0student_afk_audit.py" --teacher nexto --episodes 2 --decisions 120
) else (
 "%PY%" -u "%~dp0student_afk_audit.py" --teacher nexto --episodes 2 --decisions 120
)
if errorlevel 1 (
 echo.
 echo AUDIT ERROR - check the message above. No models changed.
)
pause
