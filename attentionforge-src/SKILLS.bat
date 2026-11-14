@echo off
cd /d "%~dp0"
if not exist runtime_python.txt (
call SETUP.bat
if errorlevel 1 exit /b 1
)
call _RUN.bat skills --run skills01
pause
