@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into your existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u replay_il_workflow.py %*
set "WORKFLOW_EXIT=%ERRORLEVEL%"
echo.
echo Workflow exit code: %WORKFLOW_EXIT%
pause
exit /b %WORKFLOW_EXIT%
