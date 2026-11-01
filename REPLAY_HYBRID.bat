@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into the existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
echo Replay-initialized hybrid training. Parent models and replay caches are preserved.
".venv\Scripts\python.exe" -u -m replay_hybrid %*
set "HYBRID_EXIT=%ERRORLEVEL%"
echo.
echo Hybrid exit code: %HYBRID_EXIT%
echo Log: data\isolated\replay_imitation\hybrid_launcher.log
pause
exit /b %HYBRID_EXIT%
