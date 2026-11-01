@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Missing .venv Python & pause & exit /b 1)
".venv\Scripts\python.exe" -u round_robin_evaluator.py --limit 2 --games-per-pair 2 --seconds 10 --all-scripted-kickoffs --report-dir round_robin_smoke_reports
pause
