@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m pip install -r replay_il\requirements.txt
pause
