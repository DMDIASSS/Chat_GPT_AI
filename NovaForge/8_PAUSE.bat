@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py pause --run laptop01
pause
