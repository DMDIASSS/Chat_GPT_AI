@echo off
cd /d "%~dp0"
if not exist runtime_python.txt (
call 0_SETUP.bat
if errorlevel 1 exit /b 1
)
set /p DF_SIDE_PYTHON=<runtime_python.txt
"%DF_SIDE_PYTHON%" -u tools\check_sides.py --run duel02
if errorlevel 1 echo SIDE_CHECK_FAILED - keep the error above; do not infer that it passed.
pause
