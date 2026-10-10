@echo off
setlocal
cd /d "%~dp0"
py -3.11 install_bridge.py
if errorlevel 1 (
 echo ERROR: Source not changed. Send this console output.
 pause
 exit /b 1
)
echo SUCCESS: Only Learner.cpp + new header were patched. Original backup was made.
pause
