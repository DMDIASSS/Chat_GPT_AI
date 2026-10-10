@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing venv & pause & exit /b 1)
echo SHORT simulator smoke test. Creates a NEW isolated run; no main league promotion.
echo Scores in smoke tests are NOT reliable. Do NOT run alongside 2-hour job.
".venv\Scripts\python.exe" -u afk_two_hour.py --smoke
pause
