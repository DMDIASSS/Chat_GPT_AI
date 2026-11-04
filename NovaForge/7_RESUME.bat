@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -u run.py train --run laptop01 --resume --steps 2000000
pause
