@echo off
setlocal
cd /d "%~dp0"
py -3.11 install_isolated_teacher.py
if errorlevel 1 (
 echo ISOLATION INSTALL FAILED. No training started.
 pause
 exit /b 1
)
echo SUCCESS: isolated teacher worker installed. Run 0_PREFLIGHT.bat and then 4_SMOKE_NEXTO.bat.
pause
