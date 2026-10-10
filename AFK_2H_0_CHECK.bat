@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: extract this package into your original Chat_GPT_AI folder.
  pause
  exit /b 1
)
echo READ-ONLY checks: main champion integrity, cycle 9, wavedash, model compatibility.
".venv\Scripts\python.exe" -u afk_two_hour.py --dry-run
if errorlevel 1 echo CHECK FAILED. Copy the above error to ChatGPT.
pause
