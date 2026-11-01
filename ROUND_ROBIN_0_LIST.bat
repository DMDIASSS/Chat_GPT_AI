@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv Python & pause & exit /b 1)
".venv\Scripts\python.exe" -u round_robin_evaluator.py --list-only --all-scripted-kickoffs
pause
