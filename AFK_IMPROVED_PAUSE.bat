@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" afk_improved_runner.py --pause
pause
