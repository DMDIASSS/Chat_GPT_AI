@echo off
cd /d "%~dp0"
if exist "..\..\.venv\Scripts\python.exe" (
 "..\..\.venv\Scripts\python.exe" hub_app.py
) else (
 python hub_app.py
)
pause
