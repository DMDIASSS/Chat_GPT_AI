@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project .venv is missing. Restore the existing training environment first.
  exit /b 1
)
if "%~1"=="" (
  echo FREESTYLE_NATIVE.bat build
  echo FREESTYLE_NATIVE.bat smoke
  echo FREESTYLE_NATIVE.bat train --run freestyle01
  echo FREESTYLE_NATIVE.bat pause --run freestyle01
  echo FREESTYLE_NATIVE.bat resume --run freestyle01
  echo FREESTYLE_NATIVE.bat status --run freestyle01
  echo FREESTYLE_NATIVE.bat monitor --run freestyle01 --wandb-mode online
  exit /b 0
)
.venv\Scripts\python.exe -u slater_freestyle.py %*
set "FREESTYLE_EXIT=%ERRORLEVEL%"
if not "%FREESTYLE_EXIT%"=="0" echo Freestyle command failed. Read the error and saved run log above.
endlocal & exit /b %FREESTYLE_EXIT%
