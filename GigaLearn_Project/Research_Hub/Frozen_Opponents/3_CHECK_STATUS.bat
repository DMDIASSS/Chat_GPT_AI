@echo off
setlocal
cd /d "%~dp0"
py -3.11 extended_rotation.py status
if errorlevel 1 echo No completed challenger checkpoint yet, or a validation error occurred.
pause
