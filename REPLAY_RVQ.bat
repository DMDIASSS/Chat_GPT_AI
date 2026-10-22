@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: Extract into the existing Chat_GPT_AI project with its .venv.
 pause
 exit /b 1
)
echo Residual-VQ replay imitation. Original models and parsed chunks are preserved.
".venv\Scripts\python.exe" -u -m replay_rvq %*
set "RVQ_EXIT=%ERRORLEVEL%"
echo.
echo RVQ exit code: %RVQ_EXIT%
echo Log: data\isolated\replay_imitation\rvq_launcher.log
pause
exit /b %RVQ_EXIT%
