@echo off
setlocal
cd /d "%~dp0"
if not exist runtime_python.txt goto missing
set /p AF_PY=<runtime_python.txt
"%AF_PY%" -u tools\setup_viewer.py
pause
exit /b
:missing
echo Run SETUP.bat first.
pause
