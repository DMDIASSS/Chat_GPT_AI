@echo off
cd /d "%~dp0"
"..\..\.venv\Scripts\python.exe" hub_cli.py plan --variants 12
pause
