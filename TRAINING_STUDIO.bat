@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing project Python. Create the project .venv first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "slater_training_studio.py"
set "studio_exit=%errorlevel%"
if not "%studio_exit%"=="0" pause
exit /b %studio_exit%
