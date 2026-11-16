@echo off
cd /d "%~dp0"
if not exist runtime_python.txt (
py -3.11 tools\setup_project.py
if errorlevel 1 exit /b 1
)
set /p DF_PYTHON=<runtime_python.txt
"%DF_PYTHON%" -u run.py %*
if errorlevel 1 (
echo DUELFORGE_COMMAND_FAILED - keep the error above. Last complete checkpoint preserved.
exit /b 1
)
