@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
 echo Existing project Python is missing. Extract into E:\Downloads\Chat_GPT_AI
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -u compare_u271_checkpoints.py audit %*
set "COMPARE_EXIT=%ERRORLEVEL%"
pause
exit /b %COMPARE_EXIT%
