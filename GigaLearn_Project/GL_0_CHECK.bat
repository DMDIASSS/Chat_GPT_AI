@echo off
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
 "..\.venv\Scripts\python.exe" scripts\manage.py check
) else (
 py -3 scripts\manage.py check
)
pause
