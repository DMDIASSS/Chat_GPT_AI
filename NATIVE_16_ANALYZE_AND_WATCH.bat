@echo off
cd /d "%~dp0"
echo Read-only inspection. Existing training can keep running.
.venv\Scripts\python.exe -u slater_native_inspect.py analyze --open
pause
