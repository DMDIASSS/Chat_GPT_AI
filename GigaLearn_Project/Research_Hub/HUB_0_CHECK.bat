@echo off
cd /d "%~dp0"
"..\..\.venv\Scripts\python.exe" hub_cli.py check
pause
