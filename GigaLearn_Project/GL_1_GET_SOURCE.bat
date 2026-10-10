@echo off
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
 "..\.venv\Scripts\python.exe" scripts\manage.py clone
) else (
 py -3 scripts\manage.py clone
)
pause
