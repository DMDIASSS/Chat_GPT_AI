@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project .venv is missing.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -u slater_freestyle.py gui --settings FREESTYLE_SETTINGS.json
set "FREESTYLE_EXIT=%ERRORLEVEL%"
if not "%FREESTYLE_EXIT%"=="0" pause
endlocal & exit /b %FREESTYLE_EXIT%
