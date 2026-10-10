@echo off
setlocal
cd /d "%~dp0"
py -3.11 extended_rotation.py stop
if errorlevel 1 (
 echo Could not request safe stop.
 pause
 exit /b 1
)
echo You may keep watching the original training window until it confirms a saved checkpoint.
pause
