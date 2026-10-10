@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv\Scripts\python.exe missing. Extract inside the Chat_GPT_AI project.
  pause
  exit /b 1
)
echo ================================================================
echo AFK 2-HOUR RUN: read-only finalist checks + isolated PPO training.
echo Does NOT change main champion or league_state.json.
echo STOP other AutoLeague jobs first, keep PC awake and plugged in.
echo Don't close this window. No administrator rights required.
echo ================================================================
".venv\Scripts\python.exe" -u afk_two_hour.py --minutes 120
if errorlevel 1 (
  echo AFK job stopped/failed. See STATUS.json in the newest data\afk_runs\timestamp folder.
) else (
  echo AFK job completed successfully. See data\afk_runs\latest timestamp folder.
)
pause
