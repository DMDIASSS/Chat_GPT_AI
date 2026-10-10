@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" afk_improved_runner.py --hours 0 --cycles 0 --eval-games 40
if errorlevel 1 pause
