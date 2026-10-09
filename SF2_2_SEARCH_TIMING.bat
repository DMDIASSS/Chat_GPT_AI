@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Extract into Chat_GPT_AI project first.& pause& exit /b 1)
".venv\Scripts\python.exe" -u sf2_search.py --seed 700 --train-seeds 4 --test-seeds 16
if errorlevel 1 echo Search problem. Send full error.
pause
