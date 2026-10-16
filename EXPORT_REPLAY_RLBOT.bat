@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into your existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u export_replay_rlbot.py %*
set "REPLAY_EXPORT_EXIT=%ERRORLEVEL%"
pause
exit /b %REPLAY_EXPORT_EXIT%
