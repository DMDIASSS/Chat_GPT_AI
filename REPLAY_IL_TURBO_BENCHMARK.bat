@echo off
setlocal
cd /d "%~dp0"
echo Replay imitation turbo runtime tuner
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Extract this update into your existing Chat_GPT_AI project.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u replay_il_turbo_benchmark.py --device cuda %*
set "TURBO_EXIT=%ERRORLEVEL%"
echo.
echo Turbo benchmark exit code: %TURBO_EXIT%
pause
exit /b %TURBO_EXIT%
