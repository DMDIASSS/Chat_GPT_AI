@echo off
setlocal
cd /d "%~dp0"
echo SLOW THOROUGH TOURNAMENT. STOP AutoLeague before starting.
if not exist ".venv\Scripts\python.exe" (echo Missing local .venv. Extract into original Chat_GPT_AI folder. & pause & exit /b 1)
".venv\Scripts\python.exe" -u model_tournament.py --thorough
if errorlevel 1 (echo Stopped or failed. Restart to reuse completed evaluations. & pause & exit /b 1)
pause
