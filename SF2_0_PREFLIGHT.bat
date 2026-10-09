@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Extract into E:\Downloads\Chat_GPT_AI first.& pause& exit /b 1)
".venv\Scripts\python.exe" -u sf2_preflight.py
if errorlevel 1 echo PRE-FLIGHT FAILED. Stop here and send the error.
pause
