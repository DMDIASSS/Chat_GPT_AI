@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo Missing existing project Python. Extract into E:\Downloads\Chat_GPT_AI.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u replay_il_runtime.py %*
set "RUNTIME_EXIT=%ERRORLEVEL%"
echo.
echo Runtime benchmark exit code: %RUNTIME_EXIT%
pause
exit /b %RUNTIME_EXIT%
