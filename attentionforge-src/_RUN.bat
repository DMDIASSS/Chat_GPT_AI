@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime_python.txt" goto missing
set /p AF_PY=<"runtime_python.txt"
if not exist "%AF_PY%" goto missing
"%AF_PY%" -u -m attentionforge.cli %*
if errorlevel 1 echo COMMAND_FAILED - keep the error above. Existing projects and saved checkpoints were preserved.
exit /b %errorlevel%
:missing
echo Run SETUP.bat first. No training started.
exit /b 1
