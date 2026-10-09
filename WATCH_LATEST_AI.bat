@echo off
setlocal
cd /d "%~dp0"
title Chat GPT AI - Latest checkpoint (fixed viewer)
echo =========================================================
echo Chat GPT AI: newest SAVED trained model vs itself
echo No installs, no hidden checks, NO training or file writes.
echo =========================================================
call :run auto
exit /b %errorlevel%
:run
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv missing. Put this BAT in E:\Downloads\Chat_GPT_AI.
  goto failed
)
if not exist "watch_latest_ai.py" (
  echo ERROR: watch_latest_ai.py missing. Copy all files from repair ZIP.
  goto failed
)
echo Model selector: %~1
echo Starting viewer now... If it errors, copy the traceback below.
".venv\Scripts\python.exe" -u watch_latest_ai.py --model %~1 --actions sample --start kickoff --speed 1 --show-every 60
set "status=%errorlevel%"
echo.
echo Viewer finished with exit code: %status%
echo Window will stay open so you can read any errors.
pause
exit /b %status%
:failed
echo.
pause
exit /b 1
