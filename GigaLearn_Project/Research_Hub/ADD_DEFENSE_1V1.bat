@echo off
setlocal
cd /d "%~dp0"
echo Applying Defense Fundamentals 1v1 preset... 
echo.
set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%PY311%" goto run
set "PY311=%~dp0..\..\.venv\Scripts\python.exe"
if exist "%PY311%" goto run
echo ERROR: Python 3.11 not found at expected locations.
echo Use: py -3.11 "%~dp0add_defense_1v1.py"
pause
exit /b 1
:run
"%PY311%" "%~dp0add_defense_1v1.py"
if errorlevel 1 (
  echo ERROR: Patch failed. No C++ changes were performed.
) else (
  echo.
  echo Reopen Research Hub to see Defense Fundamentals 1v1.
)
pause
