@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv\Scripts\python.exe. Run this from your installed Chat_GPT_AI project.
  exit /b 1
)
if "%~1"=="" (
  ".venv\Scripts\python.exe" "slater_easy.py" gui
) else (
  ".venv\Scripts\python.exe" "slater_easy.py" %*
)
exit /b %ERRORLEVEL%
