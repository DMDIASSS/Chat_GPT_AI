@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=C:\Users\almas\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON%" (
  echo Python 3.11 not found: %PYTHON%
  echo Change the PYTHON setting in this BAT to your real Python path.
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0hub_fix_ppo_batch.py"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo Batch fix failed; DO NOT BUILD until resolved.
pause
exit /b %CODE%
