@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing local .venv. Extract into original Chat_GPT_AI folder. & pause & exit /b 1)
".venv\Scripts\python.exe" -u model_tournament.py --list-only
pause
