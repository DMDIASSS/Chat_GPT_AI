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
".venv\Scripts\python.exe" -u replay_il_native_runtime.py %*
set "NATIVE_RUNTIME_EXIT=%ERRORLEVEL%"
echo.
echo Native runtime benchmark exit code: %NATIVE_RUNTIME_EXIT%
pause
exit /b %NATIVE_RUNTIME_EXIT%
