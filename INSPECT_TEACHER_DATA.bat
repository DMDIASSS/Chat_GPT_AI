@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" inspect_nexto_dataset.py
if errorlevel 1 echo ERROR: Data validation failed.
pause
