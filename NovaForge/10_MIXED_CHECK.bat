@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py fetch-teachers --names nexto,ripple,chronos,galactus
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pytest tests -q --teachers
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py doctor --teachers nexto,ripple,chronos,galactus
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py smoke --run mixed_smoke_%RANDOM% --config configs\diverse.json --workers 2
if errorlevel 1 goto failed
echo MIXED_CHECK_PASS - Next run 11_MIXED_COLLECT.bat
pause
exit /b 0
:failed
echo MIXED_CHECK_FAILED - Keep this console output for feedback.
pause
exit /b 1
