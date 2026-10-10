@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" balance_train.py --mode check
if errorlevel 1 pause
