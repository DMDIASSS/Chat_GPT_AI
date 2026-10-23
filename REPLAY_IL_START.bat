@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo Missing project .venv. Run this file from your Chat_GPT_AI project directory.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u -m replay_il.launch run %*
echo.
echo Finished. The console output is also in data\isolated\replay_imitation\launcher.log
pause
