@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The project Python environment is missing.
  pause
  exit /b 1
)
if "%~1"=="" (
  .venv\Scripts\python.exe -u export_freestyle_rlbot_v5.py --gui
) else (
  .venv\Scripts\python.exe -u export_freestyle_rlbot_v5.py %*
)
set "EXPORT_EXIT=%ERRORLEVEL%"
if not "%EXPORT_EXIT%"=="0" pause
endlocal & exit /b %EXPORT_EXIT%
