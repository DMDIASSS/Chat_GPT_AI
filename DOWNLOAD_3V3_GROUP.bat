@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into your existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u download_3v3_group.py %*
set "GROUP_EXIT=%ERRORLEVEL%"
pause
exit /b %GROUP_EXIT%
