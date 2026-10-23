@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into your existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u repair_replay_rlbot.py %*
set "REPLAY_FIX_EXIT=%ERRORLEVEL%"
pause
exit /b %REPLAY_FIX_EXIT%
