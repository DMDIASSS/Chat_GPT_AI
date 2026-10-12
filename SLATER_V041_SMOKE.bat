@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Missing .venv\Scripts\python.exe in %CD%
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u slater_v041_overnight.py smoke
if errorlevel 1 (
 echo.
 echo SMOKE FAILED. DO NOT RUN START UNTIL FIXED.
) else (
 echo.
 echo SMOKE PASSED. It is now reasonable to try START overnight.
)
pause
